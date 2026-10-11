"""Run the self-contained synthetic intelligence demonstration."""
from nykra.intelligence_demo import synthetic_demo

if __name__ == "__main__":
    import json
    print(json.dumps(synthetic_demo(), indent=2))
