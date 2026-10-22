const API_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) || '/api/v1';

export function getToken() {
  return typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('auth_token') : null;
}

export function setToken(token) {
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.setItem('auth_token', token);
  }
}

export function clearToken() {
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem('auth_token');
  }
}

async function handleResponse(res) {
  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent('auth:logout'));
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    let msg = 'API Error';
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {
      // Ignore json parse error
    }
    throw new Error(msg);
  }
  return res.json();
}

function getHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function apiGet(path) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: getHeaders()
  });
  return handleResponse(res);
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: getHeaders(),
    body: body ? JSON.stringify(body) : undefined
  });
  return handleResponse(res);
}

export async function apiPatch(path, body) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers: getHeaders(),
    body: body ? JSON.stringify(body) : undefined
  });
  return handleResponse(res);
}

export async function apiGetRaw(fullUrl) {
  const res = await fetch(fullUrl, {
    method: 'GET',
    headers: getHeaders()
  });
  return handleResponse(res);
}

// Aliases for convenience
export const get = apiGet;
export const post = apiPost;
export const patch = apiPatch;
