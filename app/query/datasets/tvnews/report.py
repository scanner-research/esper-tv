from query.datasets.prelude import *
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from scipy.stats import linregress
import statsmodels.api as sm

MALE_COLOR = 'tab:blue'
FEMALE_COLOR = 'tab:red'
MARKER_SIZE = 50


def align(col, all_dfs):
    all_cols = reduce(lambda x, y: x & y, [set(list(df[col])) for df in all_dfs])

    main_df = all_dfs[0][all_dfs[0][col].isin(all_cols)].sort_values(by=['M%']).reset_index(
        drop=True).reset_index()

    def _align(df):
        return df[df[col].isin(all_cols)].set_index(col).reindex(
            main_df[col]).reset_index().reset_index()

    return [main_df] + [_align(df) for df in all_dfs[1:]]


def screen_speak_scatter(screen_df, screen_nh_df, speak_df, speak_nh_df, col, title, plots):
    fig = plt.figure()
    ax = fig.add_subplot(111)

    ax.axhline(50, color='black', linestyle='--')

    if 'screen' in plots:
        screen_df.plot('index', 'M%', ax=ax, color=MALE_COLOR, kind='scatter', marker='s', s=MARKER_SIZE)
        screen_df.plot('index', 'F%', ax=ax, color=FEMALE_COLOR, kind='scatter', marker='s', s=MARKER_SIZE)

        if len(plots) == 1:
            pairs = list(zip(screen_df['M%'].tolist(), screen_df['F%'].tolist()))
            c = matplotlib.collections.LineCollection(
                [((i, a), (i, b)) for (i, (a, b)) in enumerate(pairs)],
                colors=[MALE_COLOR if a > b else FEMALE_COLOR for (a, b) in pairs],
                linewidths=[3 for _ in range(len(pairs))])
            ax.add_collection(c)

    if 'screen_nh' in plots:
        screen_nh_df.plot('index', 'M%', ax=ax, color=MALE_COLOR, kind='scatter', marker='x', s=MARKER_SIZE)
        screen_nh_df.plot('index', 'F%', ax=ax, color=FEMALE_COLOR, kind='scatter', marker='x', s=MARKER_SIZE)

        # print(model.summary())
        # n = len(screen_nh_df.index)
        # [intercept, slope] = model.params
        # X = screen_df['M%'].tolist()

        # ax.scatter(range(len(X)), [intercept + slope * x for x in X], color='green')
        # ax.axhline(np.mean(screen_nh_df['M%']), color='black', linestyle='--')

        # slope, intercept, r, p, _3 = linregress(screen_nh_df.index.tolist(),
        #                                         screen_nh_df['M%'].tolist())
        # ax.plot([0, n], [intercept, intercept + slope * n], color='black')
        # print(r, p)

    if 'speak' in plots:
        speak_df.plot('index', 'M%', ax=ax, color=MALE_COLOR, kind='scatter', marker='^')
        speak_df.plot('index', 'F%', ax=ax, color=FEMALE_COLOR, kind='scatter', marker='^')

    if 'speak_nh' in plots:
        # speak_nh_df.plot('index', 'M%', ax=ax, color='tab:orange', kind='scatter', marker='x')
        pass

    ax.set_ylim(0, 100)
    ax.set_ylabel('Percentage of time')
    ax.set_xlabel('')
    ax.set_xticks(range(len(screen_df[col])))
    ax.set_xticklabels(screen_df[col], rotation=45, horizontalalignment='right')
    ax.tick_params(labelsize='large')

    legends = {
        'screen': ['Screen time - male', 'Screen time - female'],
        'screen_nh': ['Screen time (no host) - male', 'Screen time (no host) - female'],
        'speak': ['Speaking time - male', 'Speaking time - female'],
        'speak_nh': ['Speaking time (no host)']
    }

    ax.legend(['50%'] + flatten([legends[p] for p in plots]))
    plt.title(title)
    plt.tight_layout()
