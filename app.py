#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time
import streamlit as st
import networkx as nx
from pyvis.network import Network
import requests
from requests.adapters import HTTPAdapter, Retry
from db import init_db, SessionLocal, User, Node, Edge
from auth_utils import verify_password
import streamlit.components.v1 as components
# ①必ず最初に
st.set_page_config(page_title='論文グラフ (Admin)', layout='wide')

# ── OpenAlex API ヘルパー ──
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429,500,502,503,504])
session.mount('https://', HTTPAdapter(max_retries=retries))
session.mount('http://', HTTPAdapter(max_retries=retries))
BASE_URL = 'https://api.openalex.org'
_metadata_cache: dict[str, dict] = {}

def get_openalex_id_from_title(title: str) -> list[tuple[str, str]]:
    resp = session.get(f"{BASE_URL}/works", params={'search': title, 'per_page': 5}, timeout=10)
    resp.raise_for_status()
    return [(r['id'].split('/')[-1], r.get('display_name','')[:200]) for r in resp.json().get('results', [])]

def fetch_metadata(openalex_id: str) -> dict:
    if openalex_id in _metadata_cache:
        return _metadata_cache[openalex_id]
    j = session.get(f"{BASE_URL}/works/{openalex_id}", timeout=10).json()
    authors = [a['author']['display_name'] for a in j.get('authorships', [])]
    year = j.get('publication_year', '?')
    label = f"{authors[0]} ({year})" if authors else f"{j.get('display_name','')[:40]}… ({year})"
    data = {'label': label, 'title': j.get('display_name',''), 'referenced': j.get('referenced_works', [])}
    _metadata_cache[openalex_id] = data
    return data

def fetch_references(openalex_id: str, max_refs: int = 100) -> set[str]:
    return set(r.split('/')[-1] for r in fetch_metadata(openalex_id)['referenced'][:max_refs])

# ── 認証処理 ──
def do_login():
    db = SessionLocal()
    user = db.query(User).filter(User.username == st.session_state.login_user).first()
    db.close()
    if user and verify_password(st.session_state.login_pass, user.hashed_password) and user.is_admin:
        st.session_state.logged_in = True
        st.session_state.user_id = user.id
    else:
        st.session_state.logged_in = False


def do_logout():
    st.session_state.logged_in = False
    st.session_state.user_id = None
    for key in ['G', 'G_loaded', 'search_results', 'login_user', 'login_pass']:
        st.session_state.pop(key, None)

# ── グラフ初期化 ──
def load_graph():
    if 'G' not in st.session_state:
        st.session_state.G = nx.DiGraph()
    if not st.session_state.get('G_loaded', False):
        db = SessionLocal()
        for n in db.query(Node).filter(Node.user_id == st.session_state.user_id):
            st.session_state.G.add_node(n.openalex_id, label=n.label, title=n.title, link=n.link)
        for e in db.query(Edge).filter(Edge.user_id == st.session_state.user_id):
            st.session_state.G.add_edge(e.source_id, e.target_id)
        db.close()
        st.session_state.G_loaded = True

# ── サイドバー UI ──
def sidebar_ui():
    st.sidebar.header('論文検索とノード追加')
    query = st.sidebar.text_input('タイトルを入力して検索', key='query')
    if st.sidebar.button('検索', key='btn_search'):
        try:
            st.session_state.search_results = get_openalex_id_from_title(query)
        except Exception as e:
            st.sidebar.error(f"検索エラー: {e}")
    if st.session_state.get('search_results'):
        for oid, title in st.session_state.search_results:
            if st.sidebar.button(f"追加: {title}", key=f"add_{oid}"):
                meta = fetch_metadata(oid)
                st.session_state.G.add_node(oid, label=meta['label'], title=meta['title'])
                db = SessionLocal()
                db.add(Node(openalex_id=oid, label=meta['label'], title=meta['title'], user_id=st.session_state.user_id))
                db.commit()
                db.close()
                st.sidebar.success(f"ノード '{meta['label']}' を追加しました。")

    st.sidebar.markdown('---')
    st.sidebar.header('矢印の自動補完')
    if st.sidebar.button('自動で引用矢印を補完', key='btn_auto_complete'):
        added = 0
        db = SessionLocal()
        for citing in list(st.session_state.G.nodes):
            for cited in fetch_references(citing):
                if cited in st.session_state.G.nodes and not st.session_state.G.has_edge(cited, citing):
                    st.session_state.G.add_edge(cited, citing)
                    db.add(Edge(source_id=cited, target_id=citing, user_id=st.session_state.user_id))
                    added += 1
        db.commit()
        db.close()
        st.sidebar.success(f"{added} 件の矢印を自動追加しました。")

    st.sidebar.markdown('---')
    st.sidebar.header('手動で矢印を追加')
    nodes = list(st.session_state.G.nodes(data=True))
    if len(nodes) >= 2:
        id2label = {nid: attrs['label'] for nid, attrs in nodes}
        src = st.sidebar.selectbox('始点ノード(引用元)', list(id2label.keys()), format_func=lambda x: id2label[x], key='manual_src')
        dst = st.sidebar.selectbox('終点ノード(引用先)', [n for n in id2label if n != src], format_func=lambda x: id2label[x], key='manual_dst')
        if st.sidebar.button('追加', key='btn_manual_add'):
            st.session_state.G.add_edge(src, dst)
            db = SessionLocal()
            db.add(Edge(source_id=src, target_id=dst, user_id=st.session_state.user_id))
            db.commit()
            db.close()
            st.sidebar.success(f"'{id2label[src]}' → '{id2label[dst]}' を追加しました。")
    else:
        st.sidebar.info('ノードが2つ以上必要です。')

    st.sidebar.markdown('---')
    st.sidebar.header('矢印の削除')
    edges = list(st.session_state.G.edges())
    if edges:
        id2label = {nid: attrs['label'] for nid, attrs in nodes}
        labels = [f"{id2label[u]} → {id2label[v]}" for u, v in edges]
        sel = st.sidebar.selectbox('削除する矢印', labels, key='del_edge')
        if st.sidebar.button('削除', key='btn_manual_del'):
            u, v = edges[labels.index(sel)]
            st.session_state.G.remove_edge(u, v)
            db = SessionLocal()
            db.query(Edge).filter(Edge.user_id == st.session_state.user_id, Edge.source_id == u, Edge.target_id == v).delete()
            db.commit()
            db.close()
            st.sidebar.success(f"'{sel}' を削除しました。")
    else:
        st.sidebar.info('削除できる矢印がありません。')

    st.sidebar.markdown('---')
    st.sidebar.header('ノード編集')
    node_ids = list(st.session_state.G.nodes)
    if node_ids:
        id2label = {nid: st.session_state.G.nodes[nid]['label'] for nid in node_ids}
        sel = st.sidebar.selectbox('編集対象ノード', node_ids, format_func=lambda x: id2label[x], key='edit_node')
        db = SessionLocal()
        node_obj = db.query(Node).filter(Node.user_id == st.session_state.user_id, Node.openalex_id == sel).first()
        new_label   = st.sidebar.text_input('ラベル',    node_obj.label,   key=f'edit_label_{sel}')
        new_title   = st.sidebar.text_input('タイトル', node_obj.title,   key=f'edit_title_{sel}')
        new_authors = st.sidebar.text_input('著者',     node_obj.authors or '', key=f'edit_authors_{sel}')
        new_link    = st.sidebar.text_input('リンク',   node_obj.link    or '', key=f'edit_link_{sel}')
        new_memo    = st.sidebar.text_area('メモ',      node_obj.memo    or '', key=f'edit_memo_{sel}')
        
        if st.sidebar.button('保存', key=f'save_node_{sel}'):
            st.session_state.G.nodes[sel].update({'label': new_label, 'title': new_title, 'link': new_link})
            node_obj.label, node_obj.title, node_obj.authors, node_obj.link, node_obj.memo = new_label, new_title, new_authors, new_link, new_memo
            db.commit()
            st.sidebar.success('ノード情報を更新しました。')
        db.close()
    else:
        st.sidebar.info('編集可能なノードがありません。')

    st.sidebar.markdown('---')
    st.sidebar.header('ノード削除')
    if node_ids:
        del_sel = st.sidebar.selectbox('削除するノード', node_ids, format_func=lambda x: id2label[x], key='del_node')
        if st.sidebar.button('削除', key='btn_node_del'):
            st.session_state.G.remove_node(del_sel)
            db = SessionLocal()
            db.query(Edge).filter(Edge.user_id == st.session_state.user_id, (Edge.source_id == del_sel) | (Edge.target_id == del_sel)).delete(synchronize_session=False)
            db.query(Node).filter(Node.user_id == st.session_state.user_id, Node.openalex_id == del_sel).delete(synchronize_session=False)
            db.commit()
            db.close()
            st.sidebar.success(f"ノード '{id2label[del_sel]}' を削除しました。")
    else:
        st.sidebar.info('削除できるノードがありません。')

# ── メイン画面：グラフ表示 ──
def show_graph():
    st.subheader('論文引用グラフ')
    net = Network(height='700px', width='100%', directed=True)
    for nid, attrs in st.session_state.G.nodes(data=True):
        node_kwargs = {'label': attrs['label'], 'title': attrs['title'], 'size': 20}
        if attrs.get('link'):
            node_kwargs['url'] = attrs['link']
        net.add_node(nid, **node_kwargs)
    for u, v in st.session_state.G.edges():
        net.add_edge(u, v, arrows='to')

    html = net.generate_html()
    click_js = """
<script type="text/javascript">
  network.on("click", function(params) {
    if (params.nodes.length > 0) {
      var node = network.body.data.nodes.get(params.nodes[0]);
      if (node.url) {
        window.open(node.url, "_blank");
      }
    }
  });
</script>
"""
    html = html.replace("</body>", click_js + "</body>")
    components.html(html, height=700)

# ── エントリポイント ──
def main():
    init_db()
    # 認証初期化
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_id = None

    # サイドバー：ログイン／ログアウト
    with st.sidebar:
        if not st.session_state.logged_in:
            st.header("ログイン (管理者のみ)")
            st.text_input("ユーザー名", key='login_user')
            st.text_input("パスワード", type="password", key='login_pass')
            st.button("ログイン", on_click=do_login)
            if 'login_user' in st.session_state and not st.session_state.logged_in:
                st.error("認証に失敗しました。管理者権限を確認してください。")
        else:
            db = SessionLocal()
            user = db.get(User, st.session_state.user_id)
            db.close()
            st.markdown(f"**ログイン中:** {user.username}")
            st.button("ログアウト", on_click=do_logout)

    if not st.session_state.logged_in:
        st.stop()

    # グラフロード＆サイドバー機能
    load_graph()
    sidebar_ui()

    # メイン表示
    show_graph()


if __name__ == "__main__":
    main()