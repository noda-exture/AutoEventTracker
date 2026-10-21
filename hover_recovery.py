"""Recover transient hover failures without claiming their measurement succeeded."""


def recover_hover(attempt_hover, next_ready):
    for attempt in range(2):
        try:
            attempt_hover()
            return 'completed'
        except Exception:
            pass
        if next_ready():
            return 'unconfirmed'
    # A missing hover never requires human input. Subsequent actions still
    # perform their own normal actionability checks and can fail independently.
    return 'unconfirmed'
