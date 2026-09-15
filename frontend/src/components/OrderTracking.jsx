import React from 'react';

const money = (value) => value == null ? '—' : `₹${Number(value).toLocaleString()}`;

function getValidActions(order, userRole) {
  const { order_status: orderStatus, payment_status: paymentStatus, last_offer_by: lastOfferBy } = order;
  if (orderStatus === 'MATCHED' || orderStatus === 'NEGOTIATING') {
    if (orderStatus === 'NEGOTIATING' && lastOfferBy === userRole) {
      return { actions: [], message: 'Waiting for the other party to respond.' };
    }
    return { actions: ['accept', 'counter'], message: null };
  }
  if (orderStatus === 'CONFIRMED' && paymentStatus !== 'ESCROW_HELD') {
    return userRole === 'buyer'
      ? { actions: ['pay'], message: null }
      : { actions: [], message: 'Waiting for buyer to complete payment.' };
  }
  if (['CONFIRMED', 'PICKUP_SCHEDULED', 'IN_TRANSIT'].includes(orderStatus)
      && paymentStatus === 'ESCROW_HELD') {
    return userRole === 'farmer'
      ? { actions: ['advance'], message: null }
      : { actions: [], message: 'Payment in escrow — waiting for farmer to ship.' };
  }
  if (orderStatus === 'DELIVERED') {
    return userRole === 'buyer'
      ? { actions: ['confirm_quality', 'reject_quality'], message: null }
      : { actions: [], message: 'Waiting for buyer to confirm receipt.' };
  }
  return { actions: [], message: `Order ${String(orderStatus || 'UNKNOWN').toLowerCase()}.` };
}

export default function OrderTracking({ order, role, counterPrice, setCounterPrice, suggestion, onAccept, onCounter, onSuggest, onPay, onAdvance, onConfirmQuality, onRejectQuality, onClose }) {
  const farmer = role === 'farmer';
  const validActions = getValidActions(order, role);
  const progress = { MATCHED: 15, NEGOTIATING: 25, CONFIRMED: 40, PICKUP_SCHEDULED: 60, IN_TRANSIT: 75, DELIVERED: 90, COMPLETED: 100 }[order.order_status] || 10;
  const paymentProgress = { NONE: 10, PENDING: 25, ESCROW_HELD: 60, RELEASED: 100, DISPUTED: 100 }[order.payment_status] || 10;
  return <section className="card order-panel">
    <div className="section-heading"><h3>4–6. {farmer ? 'Opportunity, negotiation and tracking' : 'Negotiation and order tracking'}</h3><button className="link" onClick={onClose}>Close</button></div>
    <div className="order-summary"><b>{order.crop} ({order.quantity} {order.quantity === 1 ? 'quintal' : 'quintals'}) with {farmer ? order.buyer_name : order.farmer_name}{!farmer && <span className="rating">★ {order.farmer_rating?.toFixed(1) ?? '—'}</span>}</b><span>Current offer: <strong>{money(order.current_offer_price)}</strong></span></div>
    <div className="turn-label">{validActions.message || `Your turn — choose an action below.`}</div>
    <div className="profit-grid">
      {farmer ? <>
        <div className={`profit ${order.payout_is_final ? '' : 'estimate'}`}><small>{order.payout_is_final ? 'Net farmer payout' : `Estimated net payout at ${money(order.current_offer_price)}`} {!order.payout_is_final && <span className="estimate-badge">Estimate</span>}</small><b>{order.net_farmer_payout == null ? '—' : money(order.net_farmer_payout)}</b></div>
        <div className={order.payout_is_final ? '' : 'estimate'}><small>Total amount</small><b>{money(order.total_amount)}</b></div>
        <div className={order.payout_is_final ? '' : 'estimate'}><small>Logistics</small><b>{order.logistics_cost == null ? '—' : `-${money(order.logistics_cost)}`}</b></div>
        <div className={order.payout_is_final ? '' : 'estimate'}><small>Platform fee</small><b>{order.platform_fee == null ? '—' : `-${money(order.platform_fee)}`}</b></div>
      </> : <div className="profit buyer-total"><small>{order.payment_status === 'ESCROW_HELD' || order.payment_status === 'RELEASED' ? 'Amount paid' : 'Amount to pay'}</small><b>{money(order.total_amount)}</b></div>}
    </div>
    {validActions.actions.some((action) => action === 'accept' || action === 'counter') && <div className="form-actions">
      {validActions.actions.includes('accept') && <button className="primary" onClick={onAccept}>{farmer ? "Accept Buyer's Offer" : "Accept Farmer's Price"}</button>}
      {validActions.actions.includes('counter') && <><input className="counter-input" type="number" placeholder="Counter price" value={counterPrice} onChange={(event) => setCounterPrice(event.target.value)} /><button className="secondary" onClick={onCounter}>Counter Offer</button><button className="link" onClick={onSuggest}>Suggest Counter</button></>}
    </div>}
    {suggestion && <div className="advice">{suggestion}</div>}
    <div className="tracking"><h4>Order tracking</h4>
      <div className="progress-label"><span>Order status</span><b>{order.delivery_status}</b></div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
      <div className="progress-label"><span>Payment status</span><b>{order.payment_status}</b></div>
      <div className="progress-track payment"><span style={{ width: `${paymentProgress}%` }} /></div>
      <div className="form-actions">
        {validActions.actions.includes('advance') && <button className="secondary" onClick={onAdvance}>Confirm Delivery Sent</button>}
        {validActions.actions.includes('pay') && <button className="secondary" onClick={onPay}>Pay / Hold Escrow</button>}
        {validActions.actions.includes('confirm_quality') && <button className="secondary" onClick={onConfirmQuality}>Confirm Quality</button>}
        {validActions.actions.includes('reject_quality') && <button className="secondary danger" onClick={onRejectQuality}>Reject Quality</button>}
      </div>
    </div>
  </section>;
}
