from generator.generator_analysis import analyze_default_outputs


def test_default_generator_analysis():
    response=analyze_default_outputs()
    assert response is not None