class natural_language_request:
    def __init__(self, text: str, language: str = "en"):
        self.text = text
        self.language = language

    def to_dict(self):
        return {
            "text": self.text,
            "language": self.language
        }
    
class structured_soft_constraint_request:
    def __init__(self, constraints: dict, priority: int = 1):
        self.constraints = constraints
        self.priority = priority

    def to_dict(self):
        return {
            "constraints": self.constraints,
            "priority": self.priority
        }

class structured_hard_constraint_request:
    def __init__(self, constraints: dict):
        self.constraints = constraints

    def to_dict(self):
        return {
            "constraints": self.constraints
        }

class natural_language_response:
    def __init__(self, response_text: str, confidence: float):
        self.response_text = response_text
        self.confidence = confidence

    def to_dict(self):
        return {
            "response_text": self.response_text,
            "confidence": self.confidence
        }
