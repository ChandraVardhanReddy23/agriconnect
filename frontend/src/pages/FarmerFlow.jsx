import React, { useEffect, useState } from 'react';
import { api } from '../api';
import OrderTracking from '../components/OrderTracking';
import ReactMarkdown from 'react-markdown';
import { usePhotoModal } from '../components/PhotoModal';

const money = (value) => `₹${Number(value || 0).toLocaleString()}`;

export default function FarmerFlow({ user, onLogout }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ crop: '', variety: '', quantity: '', unit: 'quintal', price: '', location: user.location || '', harvest_date: '', quality: 'standard', description: '', photo_url: '', farmer_id: user.id });
  const [listings, setListings] = useState([]);
  const [orders, setOrders] = useState([]);
  const [matches, setMatches] = useState([]);
  const [selectedListing, setSelectedListing] = useState(null);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [counterPrice, setCounterPrice] = useState('');
  const [suggestion, setSuggestion] = useState('');
  const [question, setQuestion] = useState('');
  const [advice, setAdvice] = useState('');
  const [marketAdvice, setMarketAdvice] = useState([]);
  const [logistics, setLogistics] = useState(null);
  const [message, setMessage] = useState('');
  const { setOpenPhoto, modal } = usePhotoModal();
  const set = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  async function refresh() {
    const [nextListings, nextOrders] = await Promise.all([
      api(`/listings?farmer_id=${user.id}&status=all`),
      api(`/orders?user_id=${user.id}&role=farmer`),
    ]);
    setListings(nextListings);
    setOrders(nextOrders);
    const buyerCounts = nextOrders.reduce((counts, order) => {
      counts[order.buyer_id] = (counts[order.buyer_id] || 0) + 1;
      return counts;
    }, {});
    const opportunities = await Promise.all(Object.entries(buyerCounts)
      .filter(([, count]) => count >= 2)
      .map(async ([buyerId]) => {
        try { return await api(`/logistics/optimize-routes?buyer_id=${buyerId}`); }
        catch (err) { console.error('Logistics optimization failed:', err); return null; }
      }));
    setLogistics(opportunities.filter((item) => item && item.savings > 0)
      .sort((a, b) => b.savings - a.savings)[0] || null);
    const adviceResults = await Promise.all(nextListings.slice(0, 3).map(async (listing) => {
      try {
        const result = await api(`/advisory/${encodeURIComponent(listing.crop)}/${encodeURIComponent(listing.location)}`);
        const daysToHarvest = listing.harvest_date ? Math.ceil((new Date(listing.harvest_date) - new Date()) / 86400000) : 0;
        return { ...result, crop: listing.crop, harvest_window_advice: !result.available
          ? 'Price timing will appear when regional mandi data is available.'
          : daysToHarvest > 5 && result.change_percent > 0
          ? 'Consider waiting closer to your harvest date — prices are trending up.'
          : 'Good window to sell now.' };
      } catch { return null; }
    }));
    setMarketAdvice(adviceResults.filter(Boolean));
    if (selectedOrder) setSelectedOrder(nextOrders.find((order) => order.id === selectedOrder.id) || selectedOrder);
  }
  function handlePhoto(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setForm((previous) => ({ ...previous, photo_url: reader.result }));
    reader.readAsDataURL(file);
  }
  useEffect(() => {
    refresh().catch(() => {});
  }, [user.id]);

  async function publish(event) {
    event.preventDefault(); setMessage('');
    try {
      await api('/listings/ingest', { method: 'POST', body: JSON.stringify({ ...form, quantity: Number(form.quantity), price: Number(form.price) }) });
      setMessage('Your produce is live for buyers!'); setStep(1); refresh();
    } catch (err) { setMessage(err.message); }
  }
  async function showMatches(listing) {
    try {
      setSelectedListing(listing);
      const results = await api(`/listings/${listing.id}/match`, { method: 'POST' });
      const withProfit = await Promise.all(results.map(async (match) => {
        if (!match.buyer_id) return match;
        try { return { ...match, preview_profit: await api(`/listings/${listing.id}/preview-profit?buyer_id=${match.buyer_id}`) }; } catch { return match; }
      }));
      setMatches(withProfit);
    } catch (err) { setMessage(err.message); }
  }
  async function openOrder(order) {
    setSelectedOrder(order);
    setSuggestion('');
  }
  async function orderAction(orderId, path, body) {
    try {
      const updated = await api(`/orders/${orderId}/${path}`, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) });
      setSelectedOrder(updated); await refresh();
    } catch (err) { setMessage(err.message); }
  }
  async function getSuggestion() {
    try { const result = await api(`/orders/${selectedOrder.id}/suggest-counter`); setSuggestion(`${money(result.suggested_price)} — ${result.reasoning}`); }
    catch (err) { setMessage(err.message); }
  }
  async function askAdvice(event) {
    event.preventDefault();
    try { const result = await api('/advisory', { method: 'POST', body: JSON.stringify({ farmer_id: user.id, crop: form.crop || 'my crop', question }) }); setAdvice(result.answer); }
    catch (err) { setAdvice(err.message); }
  }

  return <div className="app-shell">
    <header><div className="brand"><span>🌱</span> AgriConnect</div><div className="header-actions"><span>Hi, {user.name}</span><button className="link" onClick={onLogout}>Log out</button></div></header>
    <main className="content">
      <div className="hero"><div><p className="eyebrow">FARMER DASHBOARD</p><h2>Sell your harvest with confidence.</h2><p className="muted">List your crop, compare buyers and manage every order step.</p></div><div className="hero-icon">🚜</div></div>
      <div className="grid two">
        <section className="card"><h3>List new produce</h3><div className="steps"><span className={step >= 1 ? 'on' : ''}>1 Crop</span><span className={step >= 2 ? 'on' : ''}>2 Details</span><span className={step >= 3 ? 'on' : ''}>3 Publish</span></div>
          <form onSubmit={step < 3 ? (event) => { event.preventDefault(); setStep(step + 1); } : publish}>
            {step === 1 && <><label>What are you selling?<input name="crop" placeholder="e.g. Tomato, Onion, Wheat" value={form.crop} onChange={set} required /></label><label>Variety (optional)<input name="variety" value={form.variety} onChange={set} /></label></>}
            {step === 2 && <><div className="form-row"><label>Quantity<input name="quantity" type="number" min="1" value={form.quantity} onChange={set} required /></label><label>Unit<select name="unit" value={form.unit} onChange={set}><option>quintal</option><option>kg</option><option>tonne</option></select></label></div><label>Expected price<input name="price" type="number" min="1" value={form.price} onChange={set} required /></label><label>Location<input name="location" value={form.location} onChange={set} /></label><label>Photo (optional)<input type="file" accept="image/*" onChange={handlePhoto} /></label>{form.photo_url && <img src={form.photo_url} alt="Produce preview" className="listing-thumb" onClick={() => setOpenPhoto(form.photo_url)} />}</>}
            {step === 3 && <><div className="review"><b>{form.crop} {form.variety && `(${form.variety})`}</b><span>{form.quantity} {form.unit} · {money(form.price)}</span><span>{form.location}</span></div><label>Quality notes<textarea name="description" value={form.description} onChange={set} /></label></>}
            {message && <div className="success">{message}</div>}<div className="form-actions">{step > 1 && <button type="button" className="secondary" onClick={() => setStep(step - 1)}>Back</button>}<button className="primary">{step === 3 ? 'Publish listing' : 'Continue'}</button></div>
          </form>
        </section>
        <section className="card advisory"><h3>🌤 Crop advisor</h3><p className="muted">Ask a quick question about your crop.</p><form onSubmit={askAdvice}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="How can I prevent pests?" required /><button className="secondary">Ask advisor</button></form>{advice && <div className="advice"><ReactMarkdown>{advice}</ReactMarkdown></div>}</section>
      </div>

      {marketAdvice.length > 0 && <section className="card advisory"><h3>🌤 Proactive market guidance</h3>{marketAdvice.map((item) => <div className="advice" key={item.crop}><b>{item.crop}: {item.message}</b><br />{item.harvest_window_advice}</div>)}</section>}
      <section className="card"><div className="section-heading"><h3>My listings</h3><button className="link" onClick={refresh}>Refresh</button></div>{listings.length ? <div className="listing-list">{listings.map((item) => <div className="listing" key={item.id}>{item.photo_url ? <img src={item.photo_url} alt={item.crop} className="listing-thumb" onClick={() => setOpenPhoto(item.photo_url)} /> : <span className="crop-icon">🥬</span>}<div><b>{item.crop} {item.variety && `· ${item.variety}`}</b><small>{item.quantity} {item.unit} · {item.location}</small></div><strong>{money(item.price)}<small>{item.status}</small></strong><button className="secondary small" onClick={() => showMatches(item)}>Match buyers</button></div>)}</div> : <p className="muted">No listings yet.</p>}</section>

      {selectedListing && <section className="card"><div className="section-heading"><h3>3. Match results for {selectedListing.crop}</h3><button className="link" onClick={() => setSelectedListing(null)}>Close</button></div>{matches.length ? <div className="match-grid">{matches.map((match) => <div className="match-card" key={match.id || `${match.buyer_id}-${match.crop}`}><div className="section-heading"><div><b>{match.buyer_name}</b><small>{match.buyer_location} · Request #{match.id || match.buyer_id}</small></div><strong>{Math.round(match.total_score * 100)}%</strong></div><div className="score-bar"><span style={{ width: `${match.total_score * 100}%` }} /></div><div className="score-breakdown"><span>Price {match.score_breakdown.price_score}</span><span>Quantity {match.score_breakdown.qty_score}</span><span>Distance {match.score_breakdown.dist_score}</span><span>Quality {match.score_breakdown.quality_score}</span><span>Delivery {match.score_breakdown.delivery_score}</span></div>{match.preview_profit && <div className="advice">Estimated net payout: <b>{money(match.preview_profit.estimated_net_payout)}</b></div>}{match.id && <button className="secondary small" onClick={() => openOrder(match)}>Compare opportunity</button>}</div>)}</div> : <p className="muted">No buyer requests yet for this listing.</p>}</section>}
      {logistics && <section className="card"><h3>🚚 Logistics optimizer</h3><p className="muted">{logistics.message || `${logistics.route_order.length} nearby pickups can be combined — save ${money(logistics.savings)}.`}</p>{logistics.route_order && <small>Route: {logistics.route_order.join(' → ')}</small>}</section>}

      {orders.length > 0 && <section className="card"><div className="section-heading"><h3>My Listings — Buyer Interest</h3><button className="link" onClick={refresh}>Refresh</button></div><div className="listing-list">{orders.map((order) => <div className="listing" key={order.id}><span className="crop-icon">📩</span><div><b>{order.crop} · {order.buyer_name}</b><small>{order.quantity} · {money(order.current_offer_price || order.agreed_price)}</small></div><span className={`status ${order.status}`}>{order.status}</span><button className="primary small" onClick={() => openOrder(order)}>Open buyer request</button></div>)}</div></section>}

      {selectedOrder && <OrderTracking order={selectedOrder} role="farmer" counterPrice={counterPrice} setCounterPrice={setCounterPrice} suggestion={suggestion} onAccept={() => orderAction(selectedOrder.id, 'accept')} onCounter={() => orderAction(selectedOrder.id, 'counter', { counter_price: Number(counterPrice), by: 'farmer' })} onSuggest={getSuggestion} onAdvance={() => orderAction(selectedOrder.id, 'advance')} onClose={() => setSelectedOrder(null)} />}
      {modal}
    </main>
  </div>;
}
