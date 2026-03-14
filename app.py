import streamlit as st
import requests
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, SKOS

HEADERS = {
    "User-Agent": "skos-vocab-builder/1.0 (https://github.com/aishapectyo/skos-vocab-builder; aisha.pectyo@gmail.com)"
}
WD = Namespace("http://www.wikidata.org/entity/")

LANG_MAP = {
    "English": "en",
    "Spanish": "es",
    "Portuguese": "pt"
}

def search_concept(term, lang="en"):
    params = {"action": "wbsearchentities", "search": term,
              "language": lang, "format": "json", "limit": 1, "type": "item"}
    r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HEADERS)
    results = r.json().get("search", [])
    if not results:
        return None
    top = results[0]
    return {"id": top["id"], "label": top.get("label", ""), "description": top.get("description", "")}

def get_labels(qid, langs):
    params = {"action": "wbgetentities", "ids": qid,
              "props": "labels|aliases|descriptions",
              "languages": "|".join(langs), "format": "json"}
    r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HEADERS)
    entity = r.json()["entities"].get(qid, {})
    result = {}
    for lang in langs:
        result[lang] = {
            "pref": entity.get("labels", {}).get(lang, {}).get("value"),
            "alts": [a["value"] for a in entity.get("aliases", {}).get(lang, [])],
            "description": entity.get("descriptions", {}).get(lang, {}).get("value"),
        }
    return result

def get_relations(qid):
    def run_sparql(query, var):
        r = requests.get("https://query.wikidata.org/sparql",
                         params={"query": query, "format": "json"}, headers=HEADERS)
        results = []
        for b in r.json()["results"]["bindings"]:
            uri = b.get(var, {}).get("value", "")
            label = b.get(f"{var}Label", {}).get("value", "")
            if "/entity/Q" in uri:
                results.append({"qid": "Q" + uri.split("/entity/Q")[-1], "label": label})
        return results

    return {
        "broader": run_sparql(f"SELECT ?broader ?broaderLabel WHERE {{ wd:{qid} wdt:P279 ?broader . SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'en' . }} }} LIMIT 5", "broader"),
        "narrower": run_sparql(f"SELECT ?narrower ?narrowerLabel WHERE {{ ?narrower wdt:P279 wd:{qid} . SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'en' . }} }} LIMIT 10", "narrower"),
    }

def build_skos(qid, labels, relations, scheme_uri="http://example.org/vocab"):
    g = Graph()
    g.bind("skos", SKOS)
    g.bind("wd", WD)
    scheme = URIRef(scheme_uri)
    g.add((scheme, RDF.type, SKOS.ConceptScheme))
    concept = WD[qid]
    g.add((concept, RDF.type, SKOS.Concept))
    g.add((concept, SKOS.inScheme, scheme))
    for lang, data in labels.items():
        if data.get("pref"):
            g.add((concept, SKOS.prefLabel, Literal(data["pref"], lang=lang)))
        for alt in data.get("alts", []):
            g.add((concept, SKOS.altLabel, Literal(alt, lang=lang)))
        if data.get("description"):
            g.add((concept, SKOS.definition, Literal(data["description"], lang=lang)))
    for b in relations.get("broader", []):
        g.add((concept, SKOS.broader, WD[b["qid"]]))
    for n in relations.get("narrower", []):
        g.add((concept, SKOS.narrower, WD[n["qid"]]))
    if not relations.get("broader"):
        g.add((concept, SKOS.topConceptOf, scheme))
        g.add((scheme, SKOS.hasTopConcept, concept))
    return g

# ── UI ──────────────────────────────────────────────────────────────────
st.title("Multilingual Controlled Vocabulary Builder")
st.write("Enter a concept to look it up across languages and generate a SKOS vocabulary file.")

concept = st.text_input("Seed concept", placeholder="e.g. climate change")
selected_langs = st.multiselect("Languages", options=["English", "Spanish", "Portuguese"],
                                 default=["English", "Spanish", "Portuguese"])

if st.button("Build Vocabulary") and concept and selected_langs:
    lang_codes = [LANG_MAP[l] for l in selected_langs]

    with st.spinner("Looking up concept on Wikidata..."):
        entity = search_concept(concept)

    if not entity:
        st.error(f"No Wikidata entity found for '{concept}'. Try a different term.")
    else:
        st.success(f"Found: **{entity['id']}** — {entity['label']}")
        st.caption(entity["description"])

        with st.spinner("Fetching multilingual labels..."):
            labels = get_labels(entity["id"], lang_codes)

        with st.spinner("Fetching broader/narrower relationships..."):
            relations = get_relations(entity["id"])

        # Preview table
        st.subheader("Labels")
        for lang, data in labels.items():
            st.markdown(f"**{lang}:** {data['pref']}")
            if data["alts"]:
                st.caption("Alternates: " + ", ".join(data["alts"]))

        st.subheader("Relationships")
        if relations["broader"]:
            st.markdown("**Broader:** " + ", ".join(r["label"] for r in relations["broader"]))
        if relations["narrower"]:
            st.markdown("**Narrower:** " + ", ".join(r["label"] for r in relations["narrower"]))

        # Build and download
        g = build_skos(entity["id"], labels, relations)
        ttl = g.serialize(format="turtle")

        st.subheader("SKOS Output")
        st.code(ttl, language="turtle")

        st.download_button(
            label="⬇️ Download .ttl file",
            data=ttl,
            file_name=f"{concept.replace(' ', '_')}.ttl",
            mime="text/turtle"
        )