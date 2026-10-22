"""results/ 아래 실행 결과를 results/summary.csv 한 장으로 모읍니다.

사용법: python scripts/summarize_results.py [results 폴더 경로]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.run_summary import write_summary_csv


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "results")
    if not os.path.isdir(results_dir):
        print(f"results 폴더가 없습니다: {results_dir}")
        return 1
    path, count = write_summary_csv(results_dir)
    print(f"{count}개 실행을 요약했습니다: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
