export class ApiError extends Error {
  constructor(code, status = 0) {
    super(code);
    this.code = code; // token_expired | token_used | token_invalid | network | server_error
    this.status = status;
  }
}
