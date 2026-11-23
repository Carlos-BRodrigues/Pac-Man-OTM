class GenerationError(ValueError):
    """
    A maze could not be generated with these parameters. The message names the
    rule or parameter at fault and, where possible, a change that would work.
    """
