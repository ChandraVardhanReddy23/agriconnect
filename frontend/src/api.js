const API_URL = import.meta.env.VITE_API_URL
  || `http://${window.location.hostname}:8000/api`;

export async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Something went wrong');
  return body;
}

export const getListings = (params = '') => api(`/listings${params}`);
export const getMatches = (params) => api(`/matches?${new URLSearchParams(params)}`);
