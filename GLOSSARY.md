# Photo Meta Organizer

Indexes large photo libraries by content, so the same photo is recognised wherever it sits on disk, and keeps the user's own judgements about each photo.

## Language

**Asset**:
A unique piece of photo content, identified by the SHA-256 hash of its bytes.
_Avoid_: Image record, photo record

**File**:
One path on disk that holds an asset. An asset can have several files.
_Avoid_: Copy (as a noun for the record), location

**Photo**:
The word the interface and the API use for an asset.
_Avoid_: Image

**Duplicate**:
An asset that has more than one file.
_Avoid_: Dupe, clone

**Primary file**:
The present file of an asset with the latest last-seen time, used wherever one path is needed.

**Missing file**:
A file whose path was not found by the latest scan of its root. It stays recorded until the user asks to remove missing files.
_Avoid_: Deleted file

**Removed photo**:
An asset the user took out of the library. Its files stay on disk, and scans skip those paths.
_Avoid_: Deleted photo

**Offline root**:
A root that cannot be read, such as an unplugged drive. Its files show as missing, without an error.

**Orphan**:
An asset with no files left.

**Curation**:
What the user decides about an asset: rating, flag and labels. Extraction never changes it.
_Avoid_: User data, annotations

**Label**:
A tag the user has put on an asset.

**AI suggestion**:
A tag proposed by the model for an asset. It becomes a label only when the user accepts it.
_Avoid_: AI tag (as if it were a label)

**Scan**:
Looking through a root for files, and recording new and changed ones. Replaces "index" and "sync".

**Root**:
A folder the library scans.
