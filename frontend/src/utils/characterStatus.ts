// 인물 설명(description)에 사망이 명확히 확인된 표현이 있는지 본다. "실종"처럼
// 아직 죽음이 확정되지 않은 표현은 일부러 포함하지 않는다 — description 자체가
// 현재 읽은 위치까지 드러난 정보만 담고 있으므로(스포일러 게이팅), 이 시점에
// "사망" 계열 단어가 있다는 건 이미 확정된 사실이라는 뜻이다.
// "고인"은 뺐다 — "참고인"(예: "조심스러운 참고인 같은 존재") 같은 무관한 단어 안에
// 부분 문자열로 들어있어서 오탐(예: 살아있는 참고인을 사망자로 표시)이 났다.
const DEATH_KEYWORDS = ['사망', '숨진', '숨졌', '살해당', '피살', '타계'];

export function isDeceased(description?: string | null): boolean {
  if (!description) return false;
  return DEATH_KEYWORDS.some((keyword) => description.includes(keyword));
}
