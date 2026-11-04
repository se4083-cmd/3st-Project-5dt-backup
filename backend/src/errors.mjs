export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function requireValue(condition, status, code, message) {
  if (!condition) throw new ApiError(status, code, message);
}
