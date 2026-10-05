"""Domain errors mapped to HTTP responses in main.py."""


class AppError(Exception):
    status_code = 500

    def __init__(self, detail: str = "Internal error", **extra):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra          # machine-readable fields merged into the JSON error body


class NotFoundError(AppError):
    status_code = 404


class BadRequestError(AppError):
    status_code = 400


class ConflictError(AppError):
    status_code = 409


class InvalidTransitionError(ConflictError):
    pass


class GmailNotConnectedError(BadRequestError):
    def __init__(self):
        super().__init__("Gmail not connected. Go to Profile → Connect Gmail.")


class UploadError(BadRequestError):
    status_code = 422


class UnprocessableError(BadRequestError):
    status_code = 422


class DuplicateApplicationError(ConflictError):
    def __init__(self, existing_id: str, detail: str):
        super().__init__(detail, code="duplicate_application", existing_id=existing_id)


class SendInProgressError(ConflictError):
    def __init__(self):
        super().__init__("This email is already being sent", code="send_in_progress")


class UnverifiedRecipientError(ConflictError):
    def __init__(self, email: str):
        super().__init__(f"{email} is an unverified guess, not a confirmed recruiter address. Confirm to send anyway, or enter a real address.",
                         code="unverified_recipient")


class GmailAuthError(BadRequestError):
    def __init__(self):
        super().__init__("Gmail authorization expired or was revoked. Go to Profile → Reconnect Gmail.", code="gmail_auth")


class GmailSendError(AppError):
    """`ambiguous=True` means Gmail may still have accepted the message (timeout / 5xx)."""
    status_code = 502

    def __init__(self, detail: str = "Gmail could not send the message", ambiguous: bool = False):
        if ambiguous:
            detail += " It may or may not have been delivered — check your Gmail Sent folder before trying again."
        super().__init__(detail, code="gmail_send_failed", ambiguous=ambiguous)
        self.ambiguous = ambiguous


class IncompleteJobError(UnprocessableError, ValueError):
    """Extraction missed required fields. Still a ValueError for callers that catch that."""
