from scripts import score_ocr_cer_wer


def test_corpus_cer_and_wer_keep_punctuation_and_normalize_whitespace():
    result = score_ocr_cer_wer._score([
        ("가 나,", "가\n나,"),
        ("ABC", "ADC"),
    ])

    assert result["page_count"] == 2
    assert result["char_reference"] == 7
    assert result["char_distance"] == 1
    assert result["cer"] == round(1 / 7, 6)
    assert result["word_reference"] == 3
    assert result["word_distance"] == 1
    assert result["wer"] == round(1 / 3, 6)
