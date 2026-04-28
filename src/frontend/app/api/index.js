// src/api/index.js
import client from './client'

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const authApi = {
  register: (data) => client.post('/auth/register', data),
  login: (data) => client.post('/auth/login', data),
  refresh: (refreshToken) => client.post('/auth/refresh', { refresh_token: refreshToken }),
  me: () => client.get('/auth/me'),
}

// ---------------------------------------------------------------------------
// Movies
// ---------------------------------------------------------------------------
export const moviesApi = {
  list: (params) => client.get('/movies', { params }),
  get: (movieId) => client.get(`/movies/${movieId}`),
  genres: () => client.get('/movies/genres'),
}

// ---------------------------------------------------------------------------
// Ratings
// ---------------------------------------------------------------------------
export const ratingsApi = {
  list: (params) => client.get('/ratings', { params }),
  create: (data) => client.post('/ratings', data),
  update: (movieId, data) => client.put(`/ratings/${movieId}`, data),
  remove: (movieId) => client.delete(`/ratings/${movieId}`),
}

// ---------------------------------------------------------------------------
// Interactions
// ---------------------------------------------------------------------------
export const interactionsApi = {
  record: (data) => client.post('/interactions', data),
}

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------
export const recommendationsApi = {
  list: (params) => client.get('/recommendations', { params }),
  click: (id) => client.post(`/recommendations/${id}/click`),
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------
export const profileApi = {
  updateDisplayName: (display_name) =>
    client.patch('/profile/display-name', { display_name }),
  updatePassword: (current_password, new_password) =>
    client.patch('/profile/password', { current_password, new_password }),
  deleteAccount: (password) =>
    client.delete('/profile', { data: { password } }),
}
