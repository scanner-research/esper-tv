from query.datasets.prelude import *


def screen_speak_scatter(screen_df, screen_nh_df, speak_df, speak_nh_df, col, col_pretty):
    all_dfs = [screen_df, screen_nh_df, speak_df, speak_nh_df]

    all_cols = reduce(lambda x, y: x & y, [set(list(df[col])) for df in all_dfs])

    screen_df = screen_df[screen_df[col].isin(all_cols)].sort_values(by=['M%']).reset_index(
        drop=True).reset_index()

    def align(df):
        return df[df[col].isin(all_cols)].set_index(col).reindex(
            screen_df[col]).reset_index().reset_index()

    screen_nh_df = align(screen_nh_df)
    speak_df = align(speak_df)
    speak_nh_df = align(speak_nh_df)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    screen_df.plot('index', 'M%', ax=ax, color='tab:blue', kind='scatter', marker='s')
    screen_nh_df.plot('index', 'M%', ax=ax, color='tab:blue', kind='scatter', marker='x')
    speak_df.plot('index', 'M%', ax=ax, color='tab:orange', kind='scatter', marker='s')
    # speak_nh_df.plot('index', 'M%', ax=ax, color='tab:orange', kind='scatter', marker='x')
    ax.set_ylim(0, 100)
    ax.set_ylabel('Male %')
    ax.set_xlabel('')
    ax.set_xticks(range(len(screen_df[col])))
    ax.set_xticklabels(screen_df[col], rotation=45, horizontalalignment='right')
    ax.axhline(50, color='r', linestyle='--')
    ax.legend(['50%', 'Screen time', 'Screen time (no host)', 'Speaking time'])
    plt.title('Percentage of men by {}'.format(col_pretty))
    plt.tight_layout()
