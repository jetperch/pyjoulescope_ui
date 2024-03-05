
# Locale

The Joulescope UI supports translations.


## Adding text

When adding text, use US English.  Surround all translatable text using
the "N_" function.  You can use any string format, including multi-line
strings.  However, all newlines will be removed from the contained text.

To create paragraphs, use the "P_" function, which takes a list of
strings already surrounded by the "N_" function.   


## Process

To update the POT file:

```
pip install babel polib
python ci/translations.py
```



## References

* https://docs.python.org/3/library/gettext.html
* https://www.gnu.org/software/gettext/manual/gettext.html
* https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html
* https://www.mattlayman.com/blog/2015/i18n/
* https://babel.pocoo.org/
* https://app.transifex.com/ - Too expensive for our needs
* https://phrase.com/blog/posts/i18n-advantages-babel-python/
* https://poedit.net/
* https://www.deepl.com/translator
