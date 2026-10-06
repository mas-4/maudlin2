

def test_the_cloud_never_turns_a_headline_verb_into_a_made_up_word():
    from app.site import wordcloudgen as w
    from app.analysis.pipelines import prepare
    assert prepare('Jim Bakker dies at 86', w.PIPELINE) == 'Jim Bakker'  # once "Jim Bakker dy"
    assert prepare('Two spies caught', w.PIPELINE) == 'spy'
    assert prepare('Physics prize announced', w.PIPELINE) == 'Physics prize'
