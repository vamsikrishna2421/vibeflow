"""Tests for the adaptive vocabulary (pure learning logic)."""

from vibeflow.vocabulary import Vocabulary, is_termlike


def test_is_termlike():
    assert is_termlike("kubeCtl") is True      # CamelCase
    assert is_termlike("OAuth2") is True        # has a digit
    assert is_termlike("HTTPS") is True         # ACRONYM
    assert is_termlike("foo.bar") is True       # identifier
    assert is_termlike("Kubernetes") is False   # plain Title-case word
    assert is_termlike("hello") is False


def test_add_and_prompt():
    v = Vocabulary()
    v.add("Kubernetes", weight=5)
    v.add("kubectl", weight=3)
    prompt = v.prompt()
    assert prompt.startswith("Vocabulary:")
    assert "Kubernetes" in prompt and "kubectl" in prompt


def test_learn_from_correction_teaches_corrected_terms():
    """Real Whisper mistakes are close mis-spellings of the right term."""
    v = Vocabulary()
    learned = v.learn_from_correction(
        "deploy the Cubernetis pod using CubeCTL",
        "deploy the Kubernetes pod using kubectl",
    )
    assert "Kubernetes" in learned          # corrected spelling of a near-miss
    assert "kubectl" in learned             # lowercase jargon, learned via similarity
    p = v.prompt()
    assert "Kubernetes" in p and "kubectl" in p


def test_learn_from_single_word_correction():
    """User fixes just the one term and copies only that word."""
    v = Vocabulary()
    learned = v.learn_from_correction("connect to the CubeCTL", "kubectl")
    assert learned == ["kubectl"]


def test_learn_termlike_new_word():
    """A brand-new term-like word the user adds is learned even with no match."""
    v = Vocabulary()
    learned = v.learn_from_correction("we use REST", "we use REST and GraphQL")
    assert "GraphQL" in learned


def test_learn_ignores_stopwords_fragments_and_ordinary_words():
    """The exact class of bug from the field: never learn noise.

    Stop-words ('the'), ordinary nouns ('tool', 'report') and stray fragments
    ('alation') must never be learned when they are not the corrected spelling
    of a similar-looking mistake.
    """
    v = Vocabulary()
    learned = v.learn_from_correction("send it now", "send the report tool alation")
    assert learned == []


def test_learn_skips_words_already_in_output():
    """Words already correct in our output are not re-learned (no diff noise)."""
    v = Vocabulary()
    learned = v.learn_from_correction(
        "the Kubernetes cluster is ready",
        "the Kubernetes cluster is ready",
    )
    assert learned == []


def test_learn_terms_from_llm():
    """LLM-identified terms are added; multi-word phrases split; stop-words drop."""
    v = Vocabulary()
    learned = v.learn_terms(["Kubernetes", "kubectl", "GitHub Actions", "the"])
    assert "Kubernetes" in learned
    assert "kubectl" in learned
    assert "GitHub" in learned and "Actions" in learned   # phrase split into tokens
    assert "the" not in learned                            # stop-word rejected
    assert v.learn_terms([]) == []
    assert v.learn_terms(None) == []


def test_learn_from_text_is_conservative():
    v = Vocabulary()
    v.learn_from_text("we deployed the service using kubeCtl and OAuth2 today")
    prompt = v.prompt().lower()
    assert "kubectl" in prompt          # CamelCase term learned (kubeCtl)
    assert "oauth2" in prompt           # has-digit term learned
    assert "service" not in prompt      # ordinary words are NOT learned
    assert "today" not in prompt


def test_remove_and_list_terms():
    v = Vocabulary()
    v.add("Kubernetes", 5)
    v.add("Grafana", 4)
    assert v.list_terms() == ["Grafana", "Kubernetes"]   # sorted, case-insensitive
    assert v.remove("kubernetes") is True                # case-insensitive
    assert v.remove("nope") is False
    assert v.list_terms() == ["Grafana"]


def test_wordlist_roundtrip_and_edits(tmp_path):
    v = Vocabulary()
    for t in ("Kubernetes", "Grafana", "Atlan"):
        v.add(t, 4)
    wl = tmp_path / "my_vocabulary.txt"
    v.write_wordlist(wl)
    content = wl.read_text(encoding="utf-8")
    assert "Kubernetes" in content and content.startswith("#")  # has header + terms

    # User deletes "Atlan", adds "ArgoCD", keeps the rest.
    kept = [ln for ln in content.splitlines() if ln and not ln.startswith("#") and ln != "Atlan"]
    wl.write_text("\n".join(["# header"] + kept + ["ArgoCD"]) + "\n", encoding="utf-8")
    added, removed = v.sync_from_wordlist(wl)
    assert added == 1 and removed == 1
    terms = set(v.list_terms())
    assert "ArgoCD" in terms and "Atlan" not in terms
    assert "Kubernetes" in terms and "Grafana" in terms


def test_empty():
    v = Vocabulary()
    assert v.prompt() == ""
    assert v.learn_from_correction("", "") == []
    assert v.learn_from_text("") == 0
