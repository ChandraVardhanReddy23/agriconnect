import React, { useEffect, useState } from 'react';
import { api } from './api';
import Login from './pages/Login';
import FarmerFlow from './pages/FarmerFlow';
import BuyerFlow from './pages/BuyerFlow';

export default function App() {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('agriconnect_user')) || null; } catch { return null; }
  });

  useEffect(() => {
    if (user) localStorage.setItem('agriconnect_user', JSON.stringify(user));
    else localStorage.removeItem('agriconnect_user');
  }, [user]);

  if (!user) return <Login onLogin={setUser} />;
  const logout = () => setUser(null);
  return user.role === 'farmer'
    ? <FarmerFlow user={user} onLogout={logout} />
    : <BuyerFlow user={user} onLogout={logout} />;
}
