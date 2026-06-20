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


def test_learn_from_correction_teaches_correct_spelling():
    v = Vocabulary()
    learned = v.learn_from_correction(
        "deploy the Qbutternets pod using kubexlaplie",
        "deploy the Kubernetes pod using kubectl",
    )
    assert "Kubernetes" in learned and "kubectl" in learned
    assert "Kubernetes" in v.prompt()


def test_learn_from_text_is_conservative():
    v = Vocabulary()
    v.learn_from_text("we deployed the service using kubeCtl and OAuth2 today")
    prompt = v.prompt().lower()
    assert "kubectl" in prompt          # CamelCase term learned (kubeCtl)
    assert "oauth2" in prompt           # has-digit term learned
    assert "service" not in prompt      # ordinary words are NOT learned
    assert "today" not in prompt


def test_empty():
    v = Vocabulary()
    assert v.prompt() == ""
    assert v.learn_from_correction("", "") == []
    assert v.learn_from_text("") == 0
