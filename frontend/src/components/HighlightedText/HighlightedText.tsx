// 검색 목록에서 입력과 겹치는 글자만 눈에 띄게 합니다.
//
// 배경을 칠하면 목록이 얼룩덜룩해지므로 글자색만 바꿉니다. 대소문자는 무시합니다.
import styles from './HighlightedText.module.scss'

interface Props {
  text: string
  /** 강조할 조각. 비어 있으면 원문을 그대로 씁니다. */
  query: string
}

export default function HighlightedText({ text, query }: Props) {
  const needle = query.trim().toLowerCase()
  const at = needle === '' ? -1 : text.toLowerCase().indexOf(needle)
  if (at < 0) return text

  return (
    <>
      {text.slice(0, at)}
      <mark className={styles.hit}>{text.slice(at, at + needle.length)}</mark>
      {text.slice(at + needle.length)}
    </>
  )
}
