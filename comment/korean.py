def has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지 확인. 한글이 아니면(영문 브랜드명 등) 받침 없는 것으로 취급."""
    if not word:
        return False
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return False


def josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """word 뒤에 붙일 조사(이/가, 은/는, 을/를 등)를 받침 유무에 맞게 고른다."""
    return with_batchim if has_batchim(word) else without_batchim
