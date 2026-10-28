export const BOOK_ID = '29f8f4f6-1cff-4b13-95e3-5405a19f8b11';

export const CHUNK_BOUNDARIES = [215, 320, 380, 430] as const;

export const TYPE_LABEL: Record<string, string> = {
  person: '인물',
  ship: '선박',
  org: '조직',
  place: '장소',
};

export const TONE_LABEL: Record<string, string> = {
  ally: '우호',
  tense: '긴장',
  neutral: '중립',
};
