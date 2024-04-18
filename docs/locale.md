
# Locale

> Requires Joulescope UI 1.1.0 or newer 

The Joulescope UI supports translations for the following languages:

* **ar**: Arabic
* **de**: German
* **el**: Greek
* **es**: Spanish
* **fr**: French
* **it**: Italian
* **ja**: Japanese
* **ko**: Korean
* **zh**: Chinese (simplified)

As of 2024-04-05, we created the language translations using
[DeepL](https://www.deepl.com/) AI.  If you notice any
translation problems, please open a New Issue on
[GitHub](https://github.com/jetperch/pyjoulescope_ui/issues).
Please include the language.  For each correction, please list 
the existing language string and the recommended corrected string.
If you are comfortable with GitHub pull requests, simply open a 
pull request with the fixes to the appropriate
joulescope_ui/locale/*locale*/LC_MESSAGES/joulescope_ui.po file.

By default, the UI will use the OS language configuration.
However, you can set the LANG_JOULESCOPE_UI environment variable,
which will override the OS language.  Use the 2-letter language codes
above.  At this time, the UI only offers basic language translations
without country codes.

As of 2024-04-05, the Joulescope UI does not support further locale
customizations, such as number formats.


## Developing for Locale Support

Software that supports internationalization and localization requires
a little additional effort from software developers.


### Adding text

When adding text, use US English.  Surround all translatable text using
the "N_" function.  You can use any string format, including multi-line
strings.  However, all newlines will be removed from the contained text.

To create paragraphs, use the "P_" function, which takes a list of
strings already surrounded by the "N_" function.  You can also include
the translated strings into HTML.  Avoid using HTML markup
inside the translation strings.


### Process

To update the POT file:

```
pip install babel polib deepl
python ./ci/translations.py
```

To create a new translation, simply add the locale to 
LOCALES in ci/translations.py.


### Testing languages

To test a language, set the LANG or LANG_JOULESCOPE_UI 
environment variable before starting the Joulescope UI.

To test simplified Chinese for Windows with PowerShell:

```
$env:LANG_JOULESCOPE_UI = "zh"
python -m joulescope_ui ui
```

You can then return to English:
```
$env:LANG_JOULESCOPE_UI = "en"
python -m joulescope_ui ui
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
