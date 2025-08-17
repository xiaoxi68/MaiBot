from typing import Dict, Any
def temporarily_transform_class_to_dict(class_instance) -> Dict[str, Any]:
    return class_instance.__dict__