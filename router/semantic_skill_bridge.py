from shared.protocol.execution_common import NyraOperation,NyraResourceType
from shared.protocol.semantic import SemanticResult

class SemanticSkillBridge:
    def __init__(self,minimum_confidence:float=.80): self.minimum_confidence=float(minimum_confidence)
    def accept(self,result:SemanticResult):
        if result.confidence is None or result.confidence.score < self.minimum_confidence: return None
        if result.temporal is not None or result.triggers or result.conditions or len(result.actions)!=1: return None
        a=result.actions[0]
        if a.parameters or a.target is None or not a.target.reference.strip(): return None
        try: NyraOperation(a.operation); NyraResourceType(a.target.kind)
        except (TypeError,ValueError): return None
        return result
