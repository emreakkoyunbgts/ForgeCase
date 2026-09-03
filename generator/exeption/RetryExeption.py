class RetryException(Exception):
    """Custom exception to indicate that an operation should be retried."""
    def __init__(self,depency:str , message:str="Max retries exceeded for the operation."):
        self.depency=depency
        self.message=message
        super().__init__(self.message)