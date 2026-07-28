class ImageAnalysisError(Exception):
    """
    Raised at any stage of Gemini image analysis.

    Stages:
        empty_input       - caller passed nothing
        encoding_failed   - base64 encode blew up (corrupted bytes)
        request_error     - network / timeout
        api_error         - Gemini returned non-200
        empty_response    - candidates list was empty or malformed
        parse_error       - model returned non-JSON (retry candidate)

    Retryable: request_error, api_error (5xx), parse_error
    """
    RETRYABLE_STAGES = {"request_error", "api_error", "parse_error"}

    def __init__(self, stage: str, message: str, raw=None):
        self.stage = stage
        self.raw = raw
        super().__init__(f"[{stage}] {message}")

    @property
    def is_retryable(self) -> bool:
        return self.stage in self.RETRYABLE_STAGES
