import progressbar

def progress_bar(n):
    return progressbar.ProgressBar(max_value=n, widgets=[
        progressbar.Percentage(), ' ',
        '(', progressbar.SimpleProgress(), ')',
        ' ', progressbar.Bar(), ' ',
        progressbar.AdaptiveETA(),
    ])
