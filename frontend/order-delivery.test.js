import assert from 'node:assert/strict';
import { after, afterEach, before, mock, test } from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { createServer } from 'vite';

let server;
let OrderTracking;
let TransporterFlow;
let renderer;

before(async () => {
  server = await createServer({
    server: { middlewareMode: true },
    define: { 'import.meta.env.VITE_API_URL': JSON.stringify('https://agriconnect.test/api') },
  });
  ({ default: OrderTracking } = await server.ssrLoadModule('/src/components/OrderTracking.jsx'));
  ({ default: TransporterFlow } = await server.ssrLoadModule('/src/pages/TransporterFlow.jsx'));
});

afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = undefined;
  mock.restoreAll();
});

after(async () => server?.close());

function buttons() {
  return renderer.root.findAllByType('button');
}

function button(label) {
  return buttons().find((item) => item.children.join('') === label);
}

function order(status, paymentStatus = 'paid', id = 1) {
  return {
    id, order_status: status, payment_status: paymentStatus,
    delivery_status: status === 'CONFIRMED' ? 'placed' : status.toLowerCase(),
  };
}

async function showTransporterOrders(orders) {
  const route = {
    route_id: 'route-test', estimated_payout: 300,
    stops: [{ location: 'Nashik', orders }],
  };
  const fetchMock = mock.method(globalThis, 'fetch', async (url) => ({
    ok: true,
    json: async () => url.endsWith('/routes/available') ? [] : [route],
  }));
  await act(async () => {
    renderer = create(React.createElement(TransporterFlow, { user: { id: 3 } }));
  });
  act(() => buttons().find((item) => item.children[0] === 'My Routes (').props.onClick());
  return fetchMock;
}

test('farmer can schedule a confirmed escrowed order', () => {
  const onAdvance = mock.fn();
  act(() => {
    renderer = create(React.createElement(OrderTracking, {
      order: order('CONFIRMED', 'ESCROW_HELD'), role: 'farmer', onAdvance,
    }));
  });
  assert.ok(button('Schedule Pickup'));
  act(() => button('Schedule Pickup').props.onClick());
  assert.equal(onAdvance.mock.callCount(), 1);
});

for (const status of ['PICKUP_SCHEDULED', 'IN_TRANSIT', 'DELIVERED', 'COMPLETED', 'DISPUTED']) {
  test(`farmer delivery actions are read-only at ${status}`, () => {
    act(() => {
      renderer = create(React.createElement(OrderTracking, {
        order: order(status, 'ESCROW_HELD'), role: 'farmer', onAdvance: mock.fn(),
      }));
    });
    assert.deepEqual(buttons().map((item) => item.children.join('')), ['Close']);
    assert.ok(renderer.root.findAllByType('b')
      .some((item) => item.children.join('') === status.toLowerCase()));
  });
}

test('unpaid farmer orders cannot schedule pickup and buyers can still pay', () => {
  act(() => {
    renderer = create(React.createElement(OrderTracking, {
      order: order('CONFIRMED', 'NONE'), role: 'farmer',
    }));
  });
  assert.deepEqual(buttons().map((item) => item.children.join('')), ['Close']);
  act(() => {
    renderer.update(React.createElement(OrderTracking, {
      order: order('CONFIRMED', 'NONE'), role: 'buyer',
    }));
  });
  assert.ok(button('Pay / Hold Escrow'));
});

test('buyers cannot advance delivery and can still confirm delivered quality', () => {
  act(() => {
    renderer = create(React.createElement(OrderTracking, {
      order: order('CONFIRMED', 'ESCROW_HELD'), role: 'buyer',
    }));
  });
  assert.deepEqual(buttons().map((item) => item.children.join('')), ['Close']);
  act(() => {
    renderer.update(React.createElement(OrderTracking, {
      order: order('DELIVERED', 'ESCROW_HELD'), role: 'buyer',
    }));
  });
  assert.ok(button('Confirm Quality'));
  assert.ok(button('Reject Quality'));
});

for (const status of ['CONFIRMED', 'PICKUP_SCHEDULED']) {
  test(`transporter can pick up ${status} orders only through PhotoAction`, async () => {
    const fetchMock = await showTransporterOrders([order(status)]);
    assert.ok(button('Mark Picked Up'));
    assert.equal(button('Mark Delivered'), undefined);
    const photoAction = renderer.root.findByType('input').parent;
    await act(async () => photoAction.props.onPhoto('https://example.test/pickup.jpg'));
    const request = fetchMock.mock.calls.find(({ arguments: args }) => args[1]?.method === 'POST');
    assert.equal(request.arguments[0], 'https://agriconnect.test/api/orders/1/pickup');
    assert.deepEqual(JSON.parse(request.arguments[1].body), {
      transporter_id: 3, photo_url: 'https://example.test/pickup.jpg',
    });
  });
}

test('transporter delivers in-transit orders through PhotoAction after all pickups', async () => {
  const fetchMock = await showTransporterOrders([order('IN_TRANSIT'), order('DELIVERED', 'paid', 2)]);
  assert.ok(button('Mark Delivered'));
  assert.equal(button('Mark Picked Up'), undefined);
  const photoAction = renderer.root.findByType('input').parent;
  await act(async () => photoAction.props.onPhoto('https://example.test/deliver.jpg'));
  const request = fetchMock.mock.calls.find(({ arguments: args }) => args[1]?.method === 'POST');
  assert.equal(request.arguments[0], 'https://agriconnect.test/api/orders/1/deliver');
  assert.deepEqual(JSON.parse(request.arguments[1].body), {
    transporter_id: 3, photo_url: 'https://example.test/deliver.jpg',
  });
});

test('transporter cannot deliver while another pickup is outstanding', async () => {
  await showTransporterOrders([order('IN_TRANSIT'), order('PICKUP_SCHEDULED', 'paid', 2)]);
  assert.equal(button('Mark Delivered'), undefined);
  assert.ok(button('Mark Picked Up'));
});

for (const [status, payment] of [
  ['MATCHED', 'unpaid'], ['NEGOTIATING', 'unpaid'], ['CONFIRMED', 'unpaid'],
  ['PICKUP_SCHEDULED', 'unpaid'], ['DELIVERED', 'paid'], ['COMPLETED', 'released'],
]) {
  test(`transporter has no delivery actions for ${status}/${payment}`, async () => {
    await showTransporterOrders([order(status, payment)]);
    assert.equal(button('Mark Picked Up'), undefined);
    assert.equal(button('Mark Delivered'), undefined);
  });
}
