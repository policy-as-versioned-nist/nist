"""Private isolated invocation of the unchanged pinned FAIR engine, after SDK budgeting."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor/fair'))
import fair

if __name__ == '__main__':
    request = json.load(sys.stdin)
    state = request['scenario']['warn']
    values = fair.simulate(state['lef'], state['lm'], n=request['iterations'], seed=request['seed'])
    print(json.dumps(values, allow_nan=False, separators=(',', ':')))
