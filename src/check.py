from pathlib import Path

repo_dir = Path(__file__).parent.parent
book_dir = repo_dir / "book"
rs_dir = repo_dir / "rs"


def check_rs(name: str):
    with (book_dir / f"{name}.tsv").open(encoding="utf-8") as f_book:
        book_data = f_book.readlines()
    with (rs_dir / f"{name}.tsv").open(encoding="utf-8") as f_rs:
        rs_data = f_rs.readlines()

    book_characters = set(line.split("\t")[0] for line in book_data)
    rs_characters = set(line.split("\t")[0] for line in rs_data)

    if book_characters == rs_characters:
        print(f"{name}: good!")
    else:
        print(f"{name}: bad! {book_characters - rs_characters}")


def main():
    check_rs("u0")
    check_rs("u1")
    check_rs("q0")
    check_rs("d0")


if __name__ == "__main__":
    main()
