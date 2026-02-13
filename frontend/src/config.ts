// API configuration
// When frontend and API are served from the same domain via reverse proxy,
// use a relative path. For development, Vite proxy handles /api requests.
export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';
