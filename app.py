import streamlit as st
import requests
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, SKOS

HEADERS = {
    "User-Agent": "skos-vocab-builder/1.0 (https://github.com/aishapectyo/skos-vocab-builder; aisha.pectyo@gmail.com)"
}
WD = Namespace("http://www.wikidata.org/entity/")

LANG_MAP = {
    "English":    "en",
    "Spanish":    "es",
    "Portuguese": "pt"
}

# ── Wikidata helpers ──────────────────────────────────────────────────────────

def search_concept(term, lang="en"):
    params = {"action": "wbsearchentities", "search": term,
              "language": lang, "format": "json", "limit": 1, "type": "item"}
    r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HEADERS)
    results = r.json().get("search", [])
    if not results:
        return None
    top = results[0]
    return {"id": top["id"], "label": top.get("label", ""),
            "description": top.get("description", "")}

def get_labels(qid, langs):
    params = {"action": "wbgetentities", "ids": qid,
              "props": "labels|aliases|descriptions",
              "languages": "|".join(langs), "format": "json"}
    r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HEADERS)
    entity = r.json()["entities"].get(qid, {})
    result = {}
    for lang in langs:
        result[lang] = {
            "pref":        entity.get("labels", {}).get(lang, {}).get("value"),
            "alts":        [a["value"] for a in entity.get("aliases", {}).get(lang, [])],
            "description": entity.get("descriptions", {}).get(lang, {}).get("value"),
        }
    return result

def get_relations(qid):
    def run_sparql(query, var):
        r = requests.get("https://query.wikidata.org/sparql",
                         params={"query": query, "format": "json"}, headers=HEADERS)
        results = []
        for b in r.json()["results"]["bindings"]:
            uri   = b.get(var, {}).get("value", "")
            label = b.get(f"{var}Label", {}).get("value", "")
            if "/entity/Q" in uri:
                results.append({"qid": "Q" + uri.split("/entity/Q")[-1], "label": label})
        return results

    return {
        "broader":  run_sparql(f"SELECT ?broader ?broaderLabel WHERE {{ wd:{qid} wdt:P279 ?broader . SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'en' . }} }} LIMIT 5", "broader"),
        "narrower": run_sparql(f"SELECT ?narrower ?narrowerLabel WHERE {{ ?narrower wdt:P279 wd:{qid} . SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'en' . }} }} LIMIT 10", "narrower"),
    }

def build_skos(qid, labels, relations, scheme_uri="http://example.org/vocab"):
    g = Graph()
    g.bind("skos", SKOS)
    g.bind("wd", WD)
    scheme  = URIRef(scheme_uri)
    concept = WD[qid]
    g.add((scheme,  RDF.type,       SKOS.ConceptScheme))
    g.add((concept, RDF.type,       SKOS.Concept))
    g.add((concept, SKOS.inScheme,  scheme))
    for lang, data in labels.items():
        if data.get("pref"):
            g.add((concept, SKOS.prefLabel,  Literal(data["pref"], lang=lang)))
        for alt in data.get("alts", []):
            g.add((concept, SKOS.altLabel,   Literal(alt, lang=lang)))
        if data.get("description"):
            g.add((concept, SKOS.definition, Literal(data["description"], lang=lang)))
    for b in relations.get("broader", []):
        g.add((concept, SKOS.broader,  WD[b["qid"]]))
    for n in relations.get("narrower", []):
        g.add((concept, SKOS.narrower, WD[n["qid"]]))
    if not relations.get("broader"):
        g.add((concept, SKOS.topConceptOf, scheme))
        g.add((scheme,  SKOS.hasTopConcept, concept))
    return g

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SKOS Vocabulary Builder",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styles ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;1,8..60,300&display=swap');

html, body, [class*="css"] {
    font-family: 'Source Serif 4', Georgia, serif;
    color: #b0b0b0;
}
.stApp {
    background-color: #141414;
}

/* Header */
.app-header {
    text-align: center;
    padding: 2.5rem 1rem 1rem;
    border-bottom: 1px solid #333333;
    margin-bottom: 2rem;
}
.app-header h1 {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 2.4rem;
    font-weight: 700;
    color: #f5f5f5;
    letter-spacing: 0.02em;
    margin: 0 0 0.3rem;
    line-height: 1.15;
}
.app-header .subtitle {
    font-size: 0.9rem;
    font-weight: 300;
    font-style: italic;
    color: #707070;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.app-header .rule {
    width: 40px;
    height: 1px;
    background: #4a4a4a;
    margin: 1rem auto 0.5rem;
}

/* About block */
.about-block {
    background: #1d1d1d;
    border: 1px solid #333333;
    border-radius: 2px;
    padding: 1.4rem 1.8rem;
    margin-bottom: 2rem;
    display: flex;
    gap: 3rem;
    flex-wrap: wrap;
}
.about-intro {
    flex: 2;
    min-width: 220px;
}
.about-intro p {
    font-size: 0.88rem;
    color: #707070;
    line-height: 1.8;
    margin: 0 0 0.6rem;
    font-style: italic;
}
.about-intro p:last-child { margin: 0; }
.about-fields {
    flex: 3;
    min-width: 280px;
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem 2.5rem;
    align-content: flex-start;
}
.field-item { min-width: 180px; }
.field-name {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #b0b0b0;
    margin-bottom: 0.15rem;
}
.field-desc {
    font-size: 0.82rem;
    color: #4a4a4a;
    line-height: 1.5;
}

/* Section label */
.section-label {
    font-size: 0.68rem;
    font-weight: 400;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #4a4a4a;
    border-bottom: 1px solid #333333;
    padding-bottom: 0.5rem;
    margin-bottom: 1.2rem;
    margin-top: 1.5rem;
}

/* Result card */
.result-card {
    background: #1d1d1d;
    border: 1px solid #333333;
    border-left: 3px solid #4a4a4a;
    border-radius: 2px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
}
.result-card .rc-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.05rem;
    font-weight: 700;
    color: #f5f5f5;
    margin-bottom: 0.2rem;
}
.result-card .rc-qid {
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #4a4a4a;
    margin-bottom: 0.5rem;
}
.result-card .rc-row {
    font-size: 0.85rem;
    color: #b0b0b0;
    line-height: 1.65;
    margin-bottom: 0.2rem;
}
.result-card .rc-label {
    font-style: italic;
    color: #707070;
    margin-right: 0.3rem;
}
.result-card .rc-alts {
    font-size: 0.8rem;
    color: #4a4a4a;
    font-style: italic;
}

/* Relations */
.rel-block {
    background: #1d1d1d;
    border: 1px solid #333333;
    border-radius: 2px;
    padding: 0.9rem 1.2rem;
    margin-bottom: 0.6rem;
    font-size: 0.88rem;
    color: #b0b0b0;
    line-height: 1.7;
}
.rel-block .rel-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #707070;
    margin-bottom: 0.3rem;
}

/* Inputs */
[data-testid="stTextInput"] input {
    border: 1px solid #333333 !important;
    border-radius: 2px !important;
    background: #1d1d1d !important;
    color: #e8e8e8 !important;
    font-family: 'Source Serif 4', serif !important;
    font-size: 0.95rem !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #b0b0b0 !important;
    box-shadow: none !important;
}

/* Multiselect */
[data-testid="stMultiSelect"] > div > div {
    border: 1px solid #333333 !important;
    background: #1d1d1d !important;
    border-radius: 2px !important;
    color: #e8e8e8 !important;
}

/* Button */
[data-testid="stButton"] button {
    background-color: #1d1d1d !important;
    color: #e8e8e8 !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 2px !important;
    font-family: 'Source Serif 4', serif !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.03em !important;
}
[data-testid="stButton"] button:hover {
    border-color: #b0b0b0 !important;
    background-color: #252525 !important;
}

/* Download button */
[data-testid="stDownloadButton"] button {
    background-color: #1d1d1d !important;
    color: #e8e8e8 !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 2px !important;
    font-family: 'Source Serif 4', serif !important;
    font-size: 0.88rem !important;
}
[data-testid="stDownloadButton"] button:hover {
    border-color: #b0b0b0 !important;
    background-color: #252525 !important;
}

/* Code block */
[data-testid="stCode"] {
    border: 1px solid #333333 !important;
    border-radius: 2px !important;
}

/* Alert */
[data-testid="stAlert"] {
    background-color: #1d1d1d !important;
    border-color: #333333 !important;
    color: #b0b0b0 !important;
}

hr { border-color: #333333; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
    <div class="subtitle">Linked Data Tools</div>
    <h1>SKOS Vocabulary Builder</h1>
    <div class="rule"></div>
    <div class="subtitle">Multilingual Controlled Vocabulary Generator</div>
</div>
""", unsafe_allow_html=True)

# ── About block ───────────────────────────────────────────────────────────────

st.markdown("""
<div class="about-block">
    <div class="about-intro">
        <p>
            Enter a seed concept and this tool will look it up on Wikidata,
            retrieve its preferred labels, alternate labels, and definitions
            across your chosen languages, and map its broader and narrower
            relationships using the SKOS standard.
        </p>
        <p>
            The result is a ready-to-use Turtle (.ttl) file you can import
            into a triplestore, catalog system, or any SKOS-compatible tool.
        </p>
    </div>
    <div class="about-fields">
        <div class="field-item">
            <div class="field-name">prefLabel</div>
            <div class="field-desc">The preferred term for the concept in each language, drawn from Wikidata labels.</div>
        </div>
        <div class="field-item">
            <div class="field-name">altLabel</div>
            <div class="field-desc">Synonyms and alternate forms — sourced from Wikidata aliases.</div>
        </div>
        <div class="field-item">
            <div class="field-name">definition</div>
            <div class="field-desc">A brief scope note for the concept, taken from Wikidata descriptions.</div>
        </div>
        <div class="field-item">
            <div class="field-name">broader</div>
            <div class="field-desc">Parent concepts linked via Wikidata's subclass-of (P279) property.</div>
        </div>
        <div class="field-item">
            <div class="field-name">narrower</div>
            <div class="field-desc">Child concepts that are subclasses of the seed concept in Wikidata.</div>
        </div>
        <div class="field-item">
            <div class="field-name">topConceptOf</div>
            <div class="field-desc">Assigned automatically when no broader term is found — marks the concept as a hierarchy root.</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Input form ────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Build a vocabulary</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])
with col1:
    concept = st.text_input("Seed concept", placeholder="e.g. climate change")
with col2:
    selected_langs = st.multiselect(
        "Languages",
        options=["English", "Spanish", "Portuguese"],
        default=["English", "Spanish", "Portuguese"]
    )

st.markdown("")
run = st.button("Build Vocabulary")

# ── Results ───────────────────────────────────────────────────────────────────

if run and concept and selected_langs:
    lang_codes = [LANG_MAP[l] for l in selected_langs]

    with st.spinner("Looking up concept on Wikidata..."):
        entity = search_concept(concept)

    if not entity:
        st.error("No Wikidata entity found for '" + concept + "'. Try a different term.")
    else:
        with st.spinner("Fetching multilingual labels..."):
            labels = get_labels(entity["id"], lang_codes)

        with st.spinner("Fetching broader / narrower relationships..."):
            relations = get_relations(entity["id"])

        # ── Labels ────────────────────────────────────────────────────────────
        st.markdown('<div class="section-label">Labels</div>', unsafe_allow_html=True)

        for lang_name, lang_code in zip(selected_langs, lang_codes):
            data = labels.get(lang_code, {})
            pref = data.get("pref") or "—"
            alts = data.get("alts", [])
            defn = data.get("description") or ""
            alts_html = ('<div class="rc-alts">Alternates: ' + ", ".join(alts) + '</div>') if alts else ""
            defn_html  = ('<div class="rc-row"><span class="rc-label">Definition</span>' + defn + '</div>') if defn else ""
            st.markdown(
                '<div class="result-card">'
                '<div class="rc-qid">' + lang_name + ' &middot; ' + lang_code + '</div>'
                '<div class="rc-title">' + pref + '</div>'
                + defn_html + alts_html +
                '</div>',
                unsafe_allow_html=True
            )

        # ── Relations ─────────────────────────────────────────────────────────
        st.markdown('<div class="section-label">Relationships</div>', unsafe_allow_html=True)

        broader_text  = ", ".join(r["label"] for r in relations["broader"])  or "None found"
        narrower_text = ", ".join(r["label"] for r in relations["narrower"]) or "None found"

        st.markdown(
            '<div class="rel-block">'
            '<div class="rel-label">Broader</div>' + broader_text +
            '</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div class="rel-block">'
            '<div class="rel-label">Narrower</div>' + narrower_text +
            '</div>',
            unsafe_allow_html=True
        )

        # ── SKOS output ───────────────────────────────────────────────────────
        st.markdown('<div class="section-label">SKOS Output</div>', unsafe_allow_html=True)

        g   = build_skos(entity["id"], labels, relations)
        ttl = g.serialize(format="turtle")

        st.code(ttl, language="turtle")

        st.download_button(
            label="Download .ttl file",
            data=ttl,
            file_name=concept.replace(" ", "_") + ".ttl",
            mime="text/turtle"
        )

elif run:
    st.warning("Please enter a concept and select at least one language.")
