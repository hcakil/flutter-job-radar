"""Brave Search query templates for Flutter job discovery."""

QUERIES: list[str] = [
    # Quoted "Flutter" reduces Flutter Entertainment / random keyword bleed
    'site:linkedin.com/jobs/view "Flutter" "EMEA"',
    'site:linkedin.com/jobs/view "Flutter Developer" OR "Flutter Engineer"',
    'site:linkedin.com/jobs/view "Flutter" (remote OR Worldwide OR contractor)',
    'site:jobs.lever.co "Flutter" (Developer OR Engineer OR Dart)',
    'site:boards.greenhouse.io "Flutter" (Developer OR Engineer OR Dart)',
    'site:jobs.ashbyhq.com "Flutter" (Developer OR Engineer OR Dart)',
    'site:apply.workable.com "Flutter" (Developer OR Engineer OR Dart)',
]
