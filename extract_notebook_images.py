import base64
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote


MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


def sanitize_filename(name: str) -> str:
    """파일명에 부적절한 문자를 '_'로 바꾼다."""
    name = unquote(name)
    name = Path(name).name
    name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name)
    return name.strip("._") or "image"


def extract_images(notebook_path: Path) -> None:
    with notebook_path.open("r", encoding="utf-8") as file:
        notebook = json.load(file)

    image_dir = notebook_path.parent / "images"
    image_dir.mkdir(exist_ok=True)

    extracted_count = 0
    unresolved = []

    for cell_index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "markdown":
            continue

        source = cell.get("source", [])
        source_text = "".join(source) if isinstance(source, list) else source
        attachments = cell.get("attachments", {})

        for attachment_index, (attachment_name, mime_data) in enumerate(
            attachments.items(), start=1
        ):
            selected_mime = None
            encoded_data = None

            for mime_type, data in mime_data.items():
                if mime_type in MIME_EXTENSIONS:
                    selected_mime = mime_type
                    encoded_data = data
                    break

            if selected_mime is None or encoded_data is None:
                print(
                    f"[건너뜀] 셀 {cell_index}: "
                    f"지원하지 않는 attachment {attachment_name}"
                )
                continue

            if isinstance(encoded_data, list):
                encoded_data = "".join(encoded_data)

            extension = MIME_EXTENSIONS[selected_mime]
            original_name = sanitize_filename(attachment_name)
            stem = Path(original_name).stem

            output_name = (
                f"cell_{cell_index:03d}_"
                f"{attachment_index:02d}_{stem}{extension}"
            )
            output_path = image_dir / output_name

            if selected_mime == "image/svg+xml":
                decoded = base64.b64decode(encoded_data).decode("utf-8")
                output_path.write_text(decoded, encoding="utf-8")
            else:
                output_path.write_bytes(base64.b64decode(encoded_data))

            relative_path = f"images/{output_name}"

            # 일반 이름과 URL 인코딩된 이름을 모두 치환한다.
            possible_references = {
                attachment_name,
                unquote(attachment_name),
                quote(attachment_name, safe=""),
                quote(unquote(attachment_name), safe=""),
            }

            for reference in possible_references:
                source_text = source_text.replace(
                    f"attachment:{reference}",
                    relative_path,
                )

            extracted_count += 1
            print(f"[추출] {attachment_name} -> {relative_path}")

        # 이미지가 외부 파일로 분리됐으므로 attachment 데이터 제거
        if attachments:
            cell.pop("attachments", None)

        if isinstance(source, list):
            cell["source"] = source_text.splitlines(keepends=True)
        else:
            cell["source"] = source_text

        remaining = re.findall(
            r"attachment:([^\s)\"'>]+)",
            source_text,
        )

        for reference in remaining:
            unresolved.append((cell_index, reference))

    with notebook_path.open("w", encoding="utf-8") as file:
        json.dump(
            notebook,
            file,
            ensure_ascii=False,
            indent=1,
        )
        file.write("\n")

    print()
    print(f"추출한 이미지: {extracted_count}개")

    if unresolved:
        print("아직 해결되지 않은 attachment 참조:")
        for cell_index, reference in unresolved:
            print(f"  셀 {cell_index}: {reference}")
    else:
        print("모든 attachment 참조를 변환했습니다.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('사용법: python extract_notebook_images.py "파일명.ipynb"')
        raise SystemExit(1)

    target = Path(sys.argv[1])

    if not target.exists():
        print(f"파일을 찾을 수 없습니다: {target}")
        raise SystemExit(1)

    extract_images(target)
