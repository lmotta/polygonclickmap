![Polygon layer](./resource/avatar.jpg "Me")  

# Polygon Click Map Plugin  
![Plugin](./resource/polygonclickmap.svg "Plugin") ***Polygon Click Map*** makes it easy to create polygon from image in map.  

The ***Polygon Click Map*** is a tool plugin that permit get a delimitation of area inside the image showed on map.  
The user clicking inside the region, and the tool create automatically the limit of region.  

## Dependences:  
* [SciPy](https://www.scipy.org/install.html) . The QGIS install SciPy for Mac and Windows.  

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
        * datetime: The datetime when poligonize the region.
        * scale: Scale fo map when poligonize the region.
      * Populate the field if the group is selected.
    * Virtual area:
      * The virtual field with expression that calculate area.
      * Select the projected CRS (linear unit).
      * Create virtual field if the group is selected.
  * Adjusts border:
      * If selected, it will adjust the borders between the polygons after poligonize of regions.
  ![Ajusts border](./resources_wiki/ajustborder.gif "Adjusts border")
      * The most recent polygon will have the overlap areas cut off, and, the gap area added to its.

* **Using the tool:**    
  * Must have a visible raster layer on the map.
  * When the tool is active, the QGIS status bar has the box for the threshold used to calculate the growth region. ![Threshold](./resources_wiki/threshold_box.png "Threshold box")
  * When click in image of map, the tool will be create a growth region from this point until the neighbors pixels of image have  values greater than threshold.  
  ![Tool one click](./resources_wiki/tool_one_click.gif "Tool one click")
  * New regions can be do by clicking in the others places of the image.
  * You can change the threshold while creating the region by clicking and dragging with mouse. Right or up, the threshold increases, otherwise, the threshold decreases.  
  ![Tool drag](./resources_wiki/tool_drag.gif "Tool drag")
  * With the right mouse button you can hide or show the regions.  
  ![Tool right](./resources_wiki/tool_right.gif "Tool right")  

  * Keyboard keys:
    * D: Delete the last region.
    * U: Undoing the last deletion.
    * F: Fill holes inside the regions.
    * C: Clear regions.
    * P: Poligonize regions.
    * H: Help,press and keep hold for reading.
    
## Donation is well come.  
International (only PayPal)
[<img src="./resource/paypal.png">](https://www.paypal.com/donate?hosted_button_id=C28ATQWT4VTTQ) From Brazil ![Pix](./resource/pix.png "Pix") Key: motta.luiz@gmail



