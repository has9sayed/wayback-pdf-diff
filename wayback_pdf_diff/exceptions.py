class UndiffableContentError(ValueError):
    """
    The content provided is not a valid PDF or is otherwise
    incompatible with the requested diff algorithm.
    """


class UndecodableContentError(ValueError):
    """
    The PDF content could not be read or decoded.
    """
