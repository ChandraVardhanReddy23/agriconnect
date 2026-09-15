import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';

const money = (value) => `₹${Number(value || 0).toLocaleString()}`;

function PhotoAction({ label, onPhoto }) {
  const input = useRef(null);
  return <>
    <input
      ref={input}
      type="file"
      accept="image/*"
      capture="environment"
      hidden
      onChange={(event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => onPhoto(reader.result);
        reader.readAsDataURL(file);
      }}
    />
    <button className="secondary small" onClick={() => input.current?.click()}>{label}</button>
  </>;
}

export default function TransporterFlow({ user, onLogout }) {
  const [tab, setTab] = useState('available');
  const [available, setAvailable] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [message, setMessage] = useState('');

  async function refresh() {
    const [nextAvailable, nextRoutes] = await Promise.all([
      api('/routes/available'),
      api(`/transporter/${user.id}/routes`),
    ]);
    setAvailable(nextAvailable);
    setRoutes(nextRoutes);
  }

  useEffect(() => {
    refresh().catch((err) => setMessage(err.message));
  }, [user.id]);

  async function claim(routeId) {
    try {
      await api(`/routes/${encodeURIComponent(routeId)}/claim`, {
        method: 'POST',
        body: JSON.stringify({ transporter_id: user.id }),
      });
      setMessage('Route claimed successfully.');
      await refresh();
      setTab('routes');
    } catch (err) { setMessage(err.message); }
  }

  async function updateOrder(orderId, action, photoUrl) {
    try {
      await api(`/orders/${orderId}/${action}`, {
        method: 'POST',
        body: JSON.stringify({ transporter_id: user.id, photo_url: photoUrl }),
      });
      await refresh();
    } catch (err) { setMessage(err.message); }
  }

  const earnings = useMemo(() => routes
    .filter((route) => route.stops.every((stop) => stop.orders.every(
      (order) => ['delivered', 'completed'].includes(order.delivery_status),
    )))
    .reduce((total, route) => total + route.estimated_payout, 0), [routes]);

  return <main className="app-shell">
    <header><div className="brand"><span>🌱</span>AgriConnect</div><div className="header-actions"><span>{user.name} · Transporter</span><button className="link" onClick={onLogout}>Log out</button></div></header>
    <div className="content">
      <section className="hero"><div><p className="eyebrow">TRANSPORT OPERATIONS</p><h2>Move more produce, earn more.</h2><p className="muted">{user.vehicle_type || 'Vehicle'} · {user.vehicle_capacity || '—'} quintal capacity</p></div><div className="hero-icon">🚚</div></section>
      <section className="card"><div className="section-heading"><div><h3>Transporter dashboard</h3><span className="pill">Delivered earnings: {money(earnings)}</span></div><button className="link" onClick={() => refresh().catch((err) => setMessage(err.message))}>Refresh</button></div>
        <div className="tabs"><button className={tab === 'available' ? 'active' : ''} onClick={() => setTab('available')}>Available Routes</button><button className={tab === 'routes' ? 'active' : ''} onClick={() => setTab('routes')}>My Routes ({routes.length})</button></div>
        {message && <div className="success">{message}</div>}
        {tab === 'available' ? <div className="route-grid">{available.length ? available.map((route) => <article className="match-card" key={route.route_id}><div className="section-heading"><b>{route.route_id}</b><strong>{route.stop_count} stops</strong></div><p className="muted">{route.buyer_name} · {route.buyer_location}</p><div className="score-breakdown"><span>{route.total_distance} km</span><span>{route.total_quantity} quintals</span><span>Payout {money(route.estimated_payout)}</span></div>{route.capacity_warning && <div className="error">{route.capacity_warning_text}</div>}<button className="primary small" onClick={() => claim(route.route_id)}>Claim Route</button></article>) : <p className="muted">No consolidatable routes are available right now.</p>}</div>
          : <div className="route-list">{routes.length ? routes.map((route) => {
            const allPickedUp = route.stops.every((stop) => stop.orders.every(
              (order) => ['in_transit', 'delivered', 'completed'].includes(order.delivery_status),
            ));
            return <article className="card route-card" key={route.route_id}><div className="section-heading"><div><h3>{route.route_id}</h3><p className="muted">{route.buyer_name} · {route.buyer_location} · {route.total_distance} km</p></div><strong>{money(route.estimated_payout)}</strong></div>{route.stops.map((stop) => <div className="route-stop" key={stop.location}><div><b>{stop.farmer_name}</b><small>{stop.location} · {stop.farmer_phone || 'No phone provided'} · {stop.quantity} quintals</small></div><div className="route-orders">{stop.orders.map((order) => <div key={order.id} className="route-order">
              <span className={`status ${order.delivery_status}`}>{order.delivery_status}</span>
              {['MATCHED', 'NEGOTIATING'].includes(order.order_status)
                ? <small className="muted">Waiting for acceptance</small>
                : ['CONFIRMED', 'PICKUP_SCHEDULED'].includes(order.order_status)
                  ? order.payment_status === 'paid'
                    ? <PhotoAction label="Mark Picked Up" onPhoto={(photo) => updateOrder(order.id, 'pickup', photo)} />
                    : <small className="muted">Waiting for escrow</small>
                  : order.order_status === 'IN_TRANSIT'
                    ? allPickedUp
                      ? <PhotoAction label="Mark Delivered" onPhoto={(photo) => updateOrder(order.id, 'deliver', photo)} />
                      : <small className="muted">Waiting for all pickups</small>
                    : <small className="muted">Complete</small>}
            </div>)}</div></div>)}</article>;
          }) : <p className="muted">Claim a route to manage its stops here.</p>}</div>}
      </section>
    </div>
  </main>;
}
