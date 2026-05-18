import networkx as nx
import plotly.graph_objects as go
from collections import deque


def build_nx_from_doc_tree(doc_tree, spans, root_id=0):

    G = nx.DiGraph()
    visited = set()

    def get_size(node_id):
        try:
            return spans[node_id]["size"]
        except Exception:
            return None

    def walk(node_id, depth=0):
        if node_id in visited:
            return
        visited.add(node_id)

        node_size = get_size(node_id)
        children = doc_tree.get(node_id, [node_size, []])[1]

        G.add_node(node_id, size=node_size, depth=depth)

        for child_id, flag in children:
            child_size = get_size(child_id)
            G.add_node(child_id, size=child_size, depth=depth + 1)

            # flag belongs to the EDGE parent -> child
            G.add_edge(node_id, child_id, flag=flag)

            if child_id in doc_tree:
                walk(child_id, depth + 1)

    walk(root_id, depth=0)
    return G, root_id


def tidy_tree_layout(G, root, x_spacing=1.6, y_spacing=1.8):
   
    children = {n: list(G.successors(n)) for n in G.nodes()}

    x = {}
    next_x = 0

    def dfs(node):
        nonlocal next_x
        kids = children.get(node, [])
        if len(kids) == 0:
            x[node] = next_x
            next_x += 1
        else:
            for c in kids:
                dfs(c)
            x[node] = sum(x[c] for c in kids) / len(kids)

    dfs(root)

    depth = {root: 0}
    q = deque([root])
    while q:
        u = q.popleft()
        for v in children.get(u, []):
            depth[v] = depth[u] + 1
            q.append(v)

    xs = list(x.values()) if x else [0]
    mid_x = (min(xs) + max(xs)) / 2

    pos = {}
    for n in G.nodes():
        pos[n] = ((x.get(n, 0) - mid_x) * x_spacing, -depth.get(n, 0) * y_spacing)

    return pos, depth


def plot_doc_tree_nx_plotly(
    doc_tree,
    spans,
    root_id=0,
    show_labels=True,
    with_arrows=False,               # Plotly arrows via annotations; slow for large trees
    title="Doc Tree Visualization",
    highlight_flag_edges=True,       # Color edges by flag
    highlight_splittable_nodes=True  # Color nodes that have any outgoing flag=1 edge
):
    G, root = build_nx_from_doc_tree(doc_tree, spans, root_id=root_id)
    pos, depth_map = tidy_tree_layout(G, root)

    # -------------------------------------------------------
    # Identify "splittable parents": any outgoing edge flag=1
    # -------------------------------------------------------
    splittable_parents = set()
    for u, v, data in G.edges(data=True):
        if data.get("flag", 0) == 1:
            splittable_parents.add(u)

    # -----------------------------
    # Build edge traces
    # -----------------------------
    if highlight_flag_edges:
        edge_x0, edge_y0 = [], []
        edge_x1, edge_y1 = [], []

        for u, v, data in G.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            flag = data.get("flag", 0)

            if flag == 1:
                edge_x1 += [x0, x1, None]
                edge_y1 += [y0, y1, None]
            else:
                edge_x0 += [x0, x1, None]
                edge_y0 += [y0, y1, None]

        edge_trace_0 = go.Scatter(
            x=edge_x0, y=edge_y0,
            mode="lines",
            line=dict(width=2, color="rgba(120,120,120,0.30)"),
            hoverinfo="none",
            name="edge flag=0"
        )

        edge_trace_1 = go.Scatter(
            x=edge_x1, y=edge_y1,
            mode="lines",
            line=dict(width=3, color="rgba(255,140,0,0.60)"),
            hoverinfo="none",
            name="edge flag=1 (splittable)"
        )

        edge_traces = [edge_trace_0, edge_trace_1]
    else:
        edge_x, edge_y = [], []
        for u, v in G.edges():
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

        edge_traces = [go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=2, color="rgba(80,80,80,0.35)"),
            hoverinfo="none",
            name="edges"
        )]

    # -----------------------------
    # Build node trace
    # -----------------------------
    node_x, node_y, text, hover_text = [], [], [], []
    marker_sizes = []
    node_colors = []

    for n in G.nodes():
        x0, y0 = pos[n]
        node_x.append(x0)
        node_y.append(y0)

        size = G.nodes[n].get("size", None)
        d = depth_map.get(n, 0)
        out_deg = G.out_degree(n)

        # label inside node
        text.append(str(n) if show_labels else "")

        # hover tooltip (REAL HTML)
        hover_text.append(
            f"<b>Node:</b> {n}<br>"
            f"<b>Size:</b> {size}<br>"
            f"<b>Depth:</b> {d}<br>"
            f"<b>Children:</b> {out_deg}<br>"
            f"<b>Splittable Parent:</b> {'Yes' if n in splittable_parents else 'No'}"
        )

        # robust node size
        if size is None:
            marker_sizes.append(24)
        else:
            marker_sizes.append(22 + min(40, float(size) * 2.0))

        # node color (transparent)
        if highlight_splittable_nodes and (n in splittable_parents):
            node_colors.append("rgba(255,165,0,0.85)")  # orange
        else:
            # color by depth (transparent blue scale feel)
            # we use an rgba fallback for simple readability
            node_colors.append("rgba(31,78,121,0.25)")

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text" if show_labels else "markers",
        text=text if show_labels else None,
        textposition="middle center",
        hovertext=hover_text,
        hoverinfo="text",
        marker=dict(
            size=marker_sizes,
            color=node_colors,
            line=dict(width=2, color="#1f4e79")
        ),
        name="internal tree nodes"
    )

    # -----------------------------
    # Build figure
    # -----------------------------
    fig = go.Figure(data=[*edge_traces, node_trace])

    # Optional arrowheads via annotations (slow if many edges)
    if with_arrows:
        annotations = []
        for u, v in G.edges():
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            annotations.append(dict(
                ax=x0, ay=y0, x=x1, y=y1,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True,
                arrowhead=3,
                arrowsize=1.2,
                arrowwidth=1.4,
                arrowcolor="#444"
            ))
        fig.update_layout(annotations=annotations)

    fig.update_layout(
        title=f"{title} (root={root})",
        showlegend=True,  # ✅ show legend so flag colors are understandable
        hovermode="closest",
        margin=dict(l=20, r=20, t=60, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        template="plotly_white"
    )

    return fig