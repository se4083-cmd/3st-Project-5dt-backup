export class RagError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'RagError';
    this.code = code;
    this.details = details;
  }
}

export const reason = (code, detail) => ({ code, detail });
