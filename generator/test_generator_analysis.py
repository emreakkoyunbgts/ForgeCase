from generator.generator_analysis import analyze_default_outputs, analyze_punchy_outputs, analyze_concise_outputs


def test_default_generator_analysis():
    response=analyze_default_outputs()
    assert response is not None

def test_punchy_generator_analysis():
    response=analyze_punchy_outputs()
    assert response is not None

def test_concise_generator_analysis():
    response=analyze_concise_outputs()
    assert response is not None