# Shamela research notes: Quran 4:140

## Method

- Work only through the Shamela UI unless explicitly told otherwise.
- Use the general search first, including filters by section and century.
- Use the advanced/professional search for author, section, morphology, and logical options.
- Record every useful fragment with:
  - book/tafsir name
  - author, if visible
  - volume/page or page field as shown in Shamela
  - search query used
  - exact Arabic fragment
  - short note on relevance to Quran 4:140 and majlis/rida

## Working Queries

- `الرضا بالكفر كفر`
- `وجوب اجتناب أصحاب المعاصي`
- `فلا تقعدوا معهم حتى يخوضوا في حديث غيره إنكم إذا مثلهم`
- `شاركتموهم في الذي هم فيه`
- `رضيتم بالجلوس معهم`
- `إنكم إذا مثلهم في الإثم`
- `الراضي بالمعصية كالفاعل لها`

## Findings

### تفسير القرطبي = الجامع لأحكام القرآن

- Search query: `وجوب اجتناب أصحاب المعاصي`
- Search mode: professional search
- Scope tested: `قسم: التفسير`; author scope `مؤلف: القرطبي` was also selected, but this search still surfaced books quoting al-Qurtubi, so verify author/book scoping carefully.
- Location shown in results table: `[سورة النساء (٤): الآيات ١٤٠ إلى ١٤١]`, الجزء/الصفحة `٥/٤١٨`
- Fragment:

```arabic
فدل بهذا على وجوب اجتناب أصحاب المعاصي إذا ظهر منهم منكر، لأن من لم يجتنبهم فقد رضي فعلهم، والرضا بالكفر كفر
```

- Note: Directly connects Quran 4:140 with leaving the majlis and states the rule that rida with kufr is kufr.

### تفسير الطبري جامع البيان

- Search query: `فلا تقعدوا معهم حتى يخوضوا في حديث غيره إنكم إذا مثلهم`
- Location shown: سورة النساء 4:140; page field seen around `330`
- Fragment summary from visible text:

```arabic
فأنتم إن لم تقوموا عنهم في تلك الحال مثلهم في فعلهم
```

- Note: Explains likeness as remaining in the gathering after knowing the prohibition, while hearing kufr/istihza of Allah's ayat.

### تفسير ابن كثير

- Search query: `شاركتموهم في الذي هم فيه`
- Source shown: `تفسير ابن كثير - ط ابن الجوزي`
- Fragment:

```arabic
ورضيتم بالجلوس معهم ... وأقررتموهم على ذلك، فقد شاركتموهم في الذي هم فيه
```

- Note: Useful for tying rida with sitting in the majlis to participation in what they are upon.

### تفسير البيضاوي = أنوار التنزيل وأسرار التأويل

- Search query: `إنكم إذا مثلهم في الإثم`
- Fragment:

```arabic
إنكم إذا مثلهم في الإثم ... أو الكفر إن رضيتم بذلك
```

- Note: Distinguishes likeness in sin from kufr if there is rida with it.

Additional precise lookup:

- Search query: `أو الكفر إن رضيتم بذلك`
- Location shown in results table: `[سورة النساء (٤): الآيات ١٤٢ إلى ١٤٣]`, الجزء/الصفحة `٢/١٠٤`
- Result filters shown: `التفسير`, `القرن: ٧`
- Fragment:

```arabic
إنكم إذا مثلهم في الإثم لأنكم قادرون على الإعراض عنهم والإنكار عليهم، أو الكفر إن رضيتم بذلك
```

- Note: Important qualification: merely remaining is treated as likeness in sin because they could leave/deny; kufr is tied to rida with the kufr/istihza.

### أيسر التفاسير للجزائري

- Search query: `رضيتم بالجلوس معهم`
- Fragment seen in هداية الآيات:

```arabic
حرمة مجالسة أهل الباطل إذا كانوا يخوضون في آيات الله نقدا واستهزاء وسخرية
الرضا بالكفر كفر، والرضا بالإثم إثم
```

- Note: Clear contemporary tafsir-style conclusion on the majlis and rida rule.

### فتح الرحمن في تفسير القرآن

- Search mode: professional search
- Scope: `قسم: التفسير`
- Search query: `الرضا بالكفر كفر`
- Location shown in results table: الباب `[١٤٠]`, الجزء/الصفحة `٢/٢١٥`
- Author: not yet captured from the visible Shamela page; verify from book metadata.
- Fragment:

```arabic
إنكم إذا: أي إذا قعدتم عندهم، وسمعتم استهزاءهم، ورضيتم به، فأنتم كفار.
مثلهم: لأن الرضا بالكفر كفر.
```

- Note: Directly links sitting in the majlis, hearing istihza, being pleased with it, and kufr.

## Search UI Notes

### General search

- The top quick search creates a results tab.
- The bottom filters `جميع الأقسام` and `جميع القرون` are result filters for the current result set.
- The section list is populated from sections that appear in the current results. If the current query only returns fiqh results, the section dropdown will only show `جميع الأقسام` plus that fiqh section.
- Before running a new broad query, reset the bottom section filter back to `جميع الأقسام`; otherwise the visible result set can remain narrowed.
- For `الرضا بالكفر كفر`, general search showed `73` results before narrowing.
- The bottom `جميع القرون` filter works like the section filter: it lists only centuries present in the current result set, with result counts. Example after tafsir-focused `الرضا بالكفر كفر`: visible choices included centuries 5, 6, 7, 8, 10, 11, 13, 14, 15.

### Professional search

- Opened from the large magnifying-glass icon on the top toolbar.
- It opens the `البحث` window.
- Left pane:
  - search scope checkboxes: `المتن`, `الحواشي`, `التعليقات`, `العناوين`
  - options: `بحث صرفي`, `بحث باللواصق`, `مراعاة الهمزات`, `مراعاة التشكيل`, `مراعاة الأرقام`
  - logical mode: `البحث بكل المجموعات` or `البحث بواحدة أو أكثر`
  - five query rows, with `و / أو / ليس`
  - phrase options such as `يلزم وجود كل العبارات`, `مرنة`, `متقاربة`
- Right pane tabs:
  - `الكتب`
  - `التصنيف`
  - `المؤلفون`
  - `وفاة`
  - `المفضلة`
  - `مؤخرا`
  - `الشروح`
  - `المطالعات`
  - `السجلات`
- To restrict by section:
  1. Open `التصنيف`.
  2. Check the desired category, e.g. `التفسير`.
  3. Click `اختيار الأقسام المحددة`.
  4. The left-side scope list should show `قسم: التفسير`.
- With `قسم: التفسير` selected, searching `الرضا بالكفر كفر` returned `23` tafsir-oriented results, cleaner than the 73 general results.
- Author filtering:
  - Open `المؤلفون`.
  - Use the top filter field, e.g. `القرطبي`.
  - Select the intended author by death date when multiple names match.
  - Click `اختيار المؤلفين المحددين`.
  - Verify the left-side scope list. Example: `مؤلف: القرطبي`.
  - Needs further verification: searches with `قسم: التفسير` + `مؤلف: القرطبي` still surfaced books that quote al-Qurtubi, not only al-Qurtubi's own book. For strict source control, prefer selecting the exact book from `الكتب`, then verifying the results table.
- Death/century filtering:
  - Open `وفاة`.
  - It has two range selectors:
    - `الفترة بالقرن`: from/to centuries.
    - `الفترة بالعام`: from/to years.
  - After choosing a range, use `إضافة للمجال`.
  - This is different from the ordinary bottom `جميع القرون` dropdown: professional search lets the range be part of the search scope before running the query.
