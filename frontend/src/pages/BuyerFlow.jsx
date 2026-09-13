import React, { useEffect, useState } from 'react';
import { api } from '../api';
import OrderTracking from '../components/OrderTracking';

export default function BuyerFlow({ user, onLogout }) {
  const [demand, setDemand] = useState({ crop: '', quantity: '', unit: 'quintal', target_price: '', location: user.location || '', buyer_id: user.id });
  const [matches, setMatches] = useState([]);
  const [orders, setOrders] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [counterPrice, setCounterPrice] = useState('');
  const [suggestion, setSuggestion] = useState('');
  const [message, setMessage] = useState('');
  const set = (event) => setDemand({ ...demand, [event.target.name]: event.target.value });
  async function search(event) {
    event?.preventDefault(); setMessage('');
    try { setMatches(await api(`/matches?${new URLSearchParams({ crop: demand.crop, quantity: demand.quantity || '', location: demand.location })}`)); }
    catch (err) { setMessage(err.message); }
  }
  async function placeOrder(listing) {
    try { await api('/orders', { method: 'POST', body: JSON.stringify({ listing_id: listing.id, buyer_id: user.id, quantity: Math.min(Number(demand.quantity) || 1, listing.quantity), agreed_price: listing.price }) }); setMessage('Order request placed!'); loadOrders(); }
    catch (err) { setMessage(err.message); }
  }
  async function loadOrders() { setOrders(await api(`/orders?user_id=${user.id}&role=buyer`)); }
  function openOrder(order) { setSelectedOrder(order); setSuggestion(''); }
  async function orderAction(orderId, path, body) {
    try {
      const updated = await api(`/orders/${orderId}/${path}`, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) });
      setSelectedOrder(updated); loadOrders();
    } catch (err) { setMessage(err.message); }
  }
  async function getSuggestion() {
    try {
      const result = await api(`/orders/${selectedOrder.id}/suggest-counter`);
      setSuggestion(`₹${Number(result.suggested_price).toLocaleString()} — ${result.reasoning}`);
    } catch (err) { setMessage(err.message); }
  }
  async function postDemand(event) {
    event.preventDefault();
    try { await api('/demands', { method: 'POST', body: JSON.stringify({ ...demand, quantity: Number(demand.quantity), target_price: Number(demand.target_price || 0) }) }); setMessage('Demand shared with farmers.'); search(); }
    catch (err) { setMessage(err.message); }
  }
  useEffect(() => { loadOrders().catch(() => {}); }, []);
  return <div className="app-shell">
    <header><div className="brand"><span>🌱</span> AgriConnect</div><div className="header-actions"><span>Hi, {user.name}</span><button className="link" onClick={onLogout}>Log out</button></div></header>
    <main className="content"><div className="hero buyer-hero"><div><p className="eyebrow">BUYER DASHBOARD</p><h2>Source fresh, direct from farms.</h2><p className="muted">Tell us what you need and discover transparent, local supply.</p></div><div className="hero-icon">🧺</div></div>
      <div className="grid two"><section className="card"><h3>What do you need?</h3><form onSubmit={postDemand}><label>Crop<input name="crop" placeholder="e.g. Tomato" value={demand.crop} onChange={set} required /></label><div className="form-row"><label>Quantity<input name="quantity" type="number" min="1" value={demand.quantity} onChange={set} required /></label><label>Unit<select name="unit" value={demand.unit} onChange={set}><option>quintal</option><option>kg</option><option>tonne</option></select></label></div><label>Target price (optional)<input name="target_price" type="number" value={demand.target_price} onChange={set} placeholder="₹ per unit" /></label><label>Preferred location<input name="location" value={demand.location} onChange={set} /></label>{message && <div className="success">{message}</div>}<div className="form-actions"><button className="secondary" type="button" onClick={search}>Find matches</button><button className="primary">Post demand</button></div></form></section>
        <section className="card"><div className="section-heading"><h3>Matched produce</h3><span className="pill">{matches.length} results</span></div>{matches.length ? <div className="listing-list">{matches.map(item => <div className="listing" key={item.id}><span className="crop-icon">🥕</span><div><b>{item.crop} · {item.quality}</b><small>{item.quantity} {item.unit} · {item.location}<br />by {item.farmer_name}</small></div><div className="listing-price"><strong>₹{item.price.toLocaleString()}</strong><button className="primary small" onClick={() => placeOrder(item)}>Request</button></div></div>)}</div> : <div className="empty"><span>🔎</span><p>Search for a crop to see farmer listings.</p></div>}</section></div>
      <section className="card"><div className="section-heading"><h3>My orders</h3><button className="link" onClick={loadOrders}>Refresh</button></div>{orders.length ? orders.map(order => <div className="listing" key={order.id}><span className="crop-icon">📦</span><div><b>{order.crop}</b><small>{order.quantity} · {order.farmer_name} · ₹{Number(order.current_offer_price || order.agreed_price).toLocaleString()}</small></div><span className={`status ${order.status}`}>{order.status}</span><button className="primary small" onClick={() => openOrder(order)}>Open order</button></div>) : <p className="muted">Your placed orders will appear here.</p>}</section>
      {selectedOrder && <OrderTracking order={selectedOrder} role="buyer" counterPrice={counterPrice} setCounterPrice={setCounterPrice} suggestion={suggestion} onAccept={() => orderAction(selectedOrder.id, 'accept')} onCounter={() => orderAction(selectedOrder.id, 'counter', { counter_price: Number(counterPrice), by: 'buyer' })} onSuggest={getSuggestion} onPay={() => orderAction(selectedOrder.id, 'pay', { method: 'demo' })} onConfirmQuality={() => orderAction(selectedOrder.id, 'confirm-quality')} onRejectQuality={() => orderAction(selectedOrder.id, 'reject-quality')} onClose={() => setSelectedOrder(null)} />}
    </main>
  </div>;
}
