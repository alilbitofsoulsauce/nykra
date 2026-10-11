"""Run the isolated prospective experiment demonstration."""
import json
from nykra.prospective_demo import demo

if __name__ == '__main__':
    print(json.dumps(demo(), indent=2))
