import argparse
import json


def main():
    parser = argparse.ArgumentParser(description='Compare two plan.json exports by stable operation identity, timing and cost.')
    parser.add_argument('left', help='First plan.json path')
    parser.add_argument('right', help='Second plan.json path')
    args = parser.parse_args()
    left, right = [json.load(open(path)) for path in (args.left, args.right)]
    before = {operation['id']: operation for operation in left['operations']}
    after = {operation['id']: operation for operation in right['operations']}
    changes = [{'operation_id': key, 'before': before.get(key), 'after': after.get(key)}
               for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)]
    print(json.dumps({'left_plan': left['plan_id'], 'right_plan': right['plan_id'], 'left_cost': left['cost'],
                      'right_cost': right['cost'], 'changes': changes}, indent=2))


if __name__ == '__main__':
    main()
