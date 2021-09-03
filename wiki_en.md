![Polygon layer](./resources/avatar.jpg "Me")  

# Polygon Click Map Plugin  
![Plugin](./resources/polygonclickmap.svg "Plugin") ***Polygon Click Map*** makes it easy to create polygon from image in map.  

The ***Polygon Click Map*** is a tool plugin that permit get a delimitation of area inside the image on map.  
The user clicking inside the region, the tool create automatically the limit of region.  

## Dependences:  
* [SciPy](https://www.scipy.org/install.html) for fill holes. The QGIS install SciPy for Mac and Windows.  

## Steps:

* **Select a polygon layer editable for actived the tool:**  
![Polygon layer](./resources_wiki/polygon_editable.png "Polygon editable") ----------> ![Plugin active](./resources_wiki/plugin_active.png "Plugin activate")
* **Setup:**  
![Setup](./resources_wiki/setup.png "Setup")  ----------> ![Dialog setup](./resources_wiki/setup_dlg.png "Dialog setup")  
  * Fields:
    * Metadata:
      * List the exists text fields.
      * The selected field must have a length that is able to receive metadata from plugin.
      * The plugin populate this field with JSON format with keys:
        * rasters: List of visible raster layers.
        * user: The user of QGIS.
        * datetime: The datetime when poligonize the regions.
        * scale: Scale of map when poligonize the regions.
      * Populate the field if the group is selected.
    * Virtual area:
      * The virtual field with expression that calculate area.
      * Select the projected CRS (linear unit).
      * Create virtual field if the group is selected.
  * Growth region using diagonal pixels (8 pixels):
      * If selected, it will use the 8 neighbor pixels for calculus of growth.
  * Adjusts border:
      * If selected, it will adjust the borders between the polygons after poligonize of regions.
  ![Ajusts border](./resources_wiki/ajustborder.gif "Adjusts border")
      * The most recent polygon will have the overlap areas cut off, and, the gap area added to its.

* **Using the tool:**    
  * Must have a visible raster layer on the map.
  * When the tool is active, the QGIS status bar has the box for the threshold used to calculate the growth region. ![Threshold](./resources_wiki/threshold_box.png "Threshold box")
  * When click in image of map, the tool will be create a growth region from this point until the neighbors pixels of image that have values greater than threshold.  
  ![Tool one click](./resources_wiki/tool_one_click.gif "Tool one click")
  * New regions can be do clicking in the others places of the image.
  * Can change the threshold while creating the region, clicking and dragging with mouse. Right or up, the threshold increases, otherwise, the threshold decreases.  
  c
  * With the right mouse button, can hide or show the regions.  
  ![Tool right](./resources_wiki/tool_right.gif "Tool right")  

  * Keyboard keys:
    * D: Delete the last region.
    * U: Undoing the last deletion.
    * F: Fill holes inside the region.    
    ![Key F](./resources_wiki/key_f.gif "Key F")    
    * R: Remove all regions.
    * P: Poligonize regions. * Create the polygons.
    ![Key P](./resources_wiki/key_p.gif "Key P")
    * H: Help.
    
## Donation is well come.  
International (only PayPal)
[<img src="./resources/key_f.png">](https://www.paypal.com/donate?hosted_button_id=C28ATQWT4VTTQ) From Brazil ![Pix](./resources/pix.png "Pix") Key: motta.luiz@gmail.com