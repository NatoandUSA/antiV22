"""App version - shown in the Pipeline Health badge and reports.

Read by 10 modules (reports, health badge, selftest, timestamp), so it is a real
label, not dead weight - but it sat at "37.0" through every V37.x release and
tracked none of them. Bump it when a release ships.
"""
VERSION = "37.13"
