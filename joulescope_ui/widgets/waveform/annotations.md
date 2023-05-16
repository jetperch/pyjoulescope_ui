
# Annotations

The waveform widget provide three types of annotations:

* x-axis markers
* y-axis markers
* text

The x-axis markers apply to all plots while the y-axis markers
and text are limited to a single plot.  The annotation information
is stored in the "annotation" setting with the following structure

* next_id: The next text annotation id int
* x: The OrderedDict containing items:
  * id: The annotation id, assigned "compressed"
  * dtype: 'single' or 'dual'
  * pos1: The marker position in time64
  * pos2: For single: not present.  For dual: the second marker position in time64.
  * changed: if position changed and data request needed
  * text_pos1: The text position for marker 1, one of ['left', 'right', 'off']
  * text_pos2: The text position for marker 2, one of ['left', 'right', 'off']
* y: The list of OrderedDict, one for each plot.  Each OrderedDict contains:
  * id: The annotation id, assigned "compressed"
  * dtype: 'single' or 'dual'
  * pos1: The marker position in y-axis coordinates.
  * pos2: 
    For single: not present or None.
    For dual: the second marker position in y-axis coordinates.
  * plot_index: The plot index in range(6)
* text: The list of lists, one for each plot,
  each containing a dict.  The dict is:
  * x_lookup: np.ndarray with rows for x, id_int
  * x_lookup_length: The actual number of entries in x_lookup.
    Extra entries may be allocated but unoccupied.
  * items: the dict mapping id to text dict.  The text 
    dict has the following structure:
    * id: The annotation id
    * plot_index: The plot index in range(6)
    * text: The text string for this annotation
    * text_show: True to show the text, False to hide
    * shape: The integer shape index
    * x: The i64 timestamp for this annotation
    * y: The y-axis signal value for the annotation. 
    * y_mode: Where to display the annotation, which is
      one of ['manual', 'centered']

    Additional potential future keys include: 
    * shape_size
    * shape_color
    * text_font
    * text_size

The preferred way to save annotations is in 
an ".anno.jls" file.
"""
