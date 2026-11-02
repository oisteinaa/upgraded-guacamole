"""House matplotlib style — Nord + IBM Plex, light/dark figure pairs.

Usage:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fig_style import RC, palette, frame

    plt.rcParams.update(RC)
    for dark in (False, True):
        P = palette(dark)
        fig, ax = plt.subplots(figsize=(11, 4.8), dpi=135)
        fig.patch.set_facecolor(P["bg"])
        ...plot with P["blue"] etc...
        frame(ax, P)
        fig.tight_layout()
        fig.savefig(f"name_{'dark' if dark else 'light'}.png", facecolor=P["bg"])

If IBM Plex Sans was just installed (ttf-ibm-plex), delete
~/.cache/matplotlib/fontlist-*.json first or matplotlib won't see it.
"""

RC = {
    "font.family": "IBM Plex Sans",
    "font.size": 13,
    "axes.titlesize": 16,
    "axes.titleweight": "bold",
    "axes.labelsize": 14,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 12.5,
    "axes.titlepad": 14,
}


def palette(dark: bool) -> dict:
    """Nord palette per theme. Data in blue; red/orange for thresholds."""
    if dark:
        return dict(bg="#2e3440", fg="#d8dee9", dim="#9aa5b5", grid="#3b4252",
                    blue="#81a1c1", red="#d06f79", orange="#d08770",
                    cyan="#88c0d0", purple="#b48ead", yellow="#ebcb8b",
                    green="#a3be8c")
    return dict(bg="#ffffff", fg="#4c566a", dim="#7b88a1", grid="#e5e9f0",
                blue="#5e81ac", red="#bf616a", orange="#d08770",
                cyan="#5e81ac", purple="#a0759a", yellow="#d0a95b",
                green="#4c8a5f")


def frame(ax, P: dict) -> None:
    """Apply the house axes treatment after plotting."""
    ax.set_facecolor(P["bg"])
    for s in ax.spines.values():
        s.set_color(P["grid"])
    ax.tick_params(colors=P["fg"])
    ax.grid(color=P["grid"], lw=0.7, zorder=0)
    ax.xaxis.label.set_color(P["fg"])
    ax.yaxis.label.set_color(P["fg"])
    ax.title.set_color(P["fg"])
    leg = ax.get_legend()
    if leg is not None:
        for txt in leg.get_texts():
            txt.set_color(P["fg"])
