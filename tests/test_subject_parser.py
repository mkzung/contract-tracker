from app.subject_parser import parse_subject, strip_reply_prefixes


def test_strip_reply_prefixes():
    assert strip_reply_prefixes("Re: На согласование: ...") == "На согласование: ..."
    assert strip_reply_prefixes("RE: Fwd: RE: foo") == "foo"
    assert strip_reply_prefixes("foo") == "foo"


def test_parse_standard_subject():
    s = "На согласование: договор с ООО Альфа на устройство перегородок и отделку (Москва, Объект-А)"
    info = parse_subject(s)
    assert info.is_approval_subject is True
    assert info.contractor == "ООО Альфа"
    assert info.subject_matter == "устройство перегородок и отделку"
    assert info.region == "Москва"
    assert info.object_name == "Объект-А"


def test_parse_single_region():
    info = parse_subject("На согласование: договор с ИП Иванов на устройство ростверков (Казань)")
    assert info.region == "Казань"
    assert info.object_name is None


def test_parse_with_quotes():
    info = parse_subject('Re: На согласование: договор с ООО "Бета" на сети (Москва, Объект-Б)')
    assert info.is_approval_subject is True
    assert "Бета" in info.contractor
    assert info.region == "Москва"
    assert info.object_name == "Объект-Б"


def test_parse_non_approval():
    info = parse_subject("Привет, проверь документ")
    assert info.is_approval_subject is False
