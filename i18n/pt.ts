<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="pt_BR">
<context>
    <name>DialogSetup</name>
    <message>
        <location filename="../dialog_setup.py" line="101"/>
        <source>Fields</source>
        <translation>Campos</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="140"/>
        <source>Invalid CRS(need be projected)</source>
        <translation>Inválido SCR(precisa ser projetado)</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="144"/>
        <source>Layer: {}</source>
        <translation>Camada: {}</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="187"/>
        <source>Metadata</source>
        <translation>Metadado</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="193"/>
        <source>Field name:</source>
        <translation>Nome do campo:</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="218"/>
        <source>Virtual area(ha)</source>
        <translation>Área virtual(ha)</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="250"/>
        <source>Metadata field is empty. Create a text field in layer.</source>
        <translation>Campo de metadado está vazio. Crie um campo do tipo texto na camada.</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="268"/>
        <source>Virtual area is empty</source>
        <translation>Área virtual está  vazia</translation>
    </message>
    <message>
        <location filename="../dialog_setup.py" line="104"/>
        <source>Adjusts border</source>
        <translation>Ajustar a borda</translation>
    </message>
</context>
<context>
    <name>PolygonClickMapPlugin</name>
    <message>
        <location filename="../plugin.py" line="69"/>
        <source>Create polygon by clicking on the map. * Only for editable layers.</source>
        <translation>Cria polígonos clicando no mapa. * Apenas para camadas editáveis.</translation>
    </message>
    <message>
        <location filename="../plugin.py" line="89"/>
        <source>Setup</source>
        <translation type="obsolete">Configuração</translation>
    </message>
    <message>
        <location filename="../plugin.py" line="169"/>
        <source>Missing &apos;scipy&apos; libray. Need install scipy(https://www.scipy.org/install.html)</source>
        <translation>Faltando biblioteca &apos;scipy&apos;. Precisa instalar scipy(https://www.scipy.org/install.html)</translation>
    </message>
    <message>
        <location filename="../plugin.py" line="96"/>
        <source>Setup...</source>
        <translation>Configuração...</translation>
    </message>
    <message>
        <location filename="../plugin.py" line="100"/>
        <source>About...</source>
        <translation>Sobre...</translation>
    </message>
    <message>
        <location filename="../plugin.py" line="152"/>
        <source>{} - About</source>
        <translation>{} - Sobre</translation>
    </message>
</context>
<context>
    <name>PolygonClickMapTool</name>
    <message>
        <location filename="../polygonclickmap.py" line="436"/>
        <source>Missing raster layer visible in Map</source>
        <translation>Faltando camada de imagem visível no Mapa</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="486"/>
        <source>Missing polygon layer to receive</source>
        <translation>Faltando camada de polígonos para receber</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="558"/>
        <source>Polygonize - Missing features</source>
        <translation>Poligonalização - Faltando feições</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="560"/>
        <source>Polygonize - {} features added</source>
        <translation>Poligonalização - {} feições adicionadas</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="517"/>
        <source>Current layer is</source>
        <translation>Camada atual é</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="689"/>
        <source>images</source>
        <translation>imagens</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="552"/>
        <source>Add features from images to</source>
        <translation>Adicionar feições a partir das imagens para</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="566"/>
        <source>Delete {} images</source>
        <translation>Deletado {} imagens</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="655"/>
        <source>{} images</source>
        <translation>{} imagens</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="659"/>
        <source>Treshold</source>
        <translation>Tolerância</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="661"/>
        <source>(pixel RGB)</source>
        <translation>(pixel RGB)</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="700"/>
        <source>Canceled by user</source>
        <translation>Cancelado pelo usuário</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="692"/>
        <source>{} - Last image added {} pixels</source>
        <translation>{} - Ultima imagem adicionada {} pixeis</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="695"/>
        <source>{} - Not added images( no pixels found)</source>
        <translation>{} - Nao foi adicionada imagens( não foi encontrado pixeis)</translation>
    </message>
    <message>
        <location filename="../polygonclickmap.py" line="577"/>
        <source>
        *** HELP - {} ***
        Create polygon by clicking on the map image

        Steps:
        - Creating an Image of growth.
         . The tool create a image of growth from the clicked point, seed point, in the map.
         . The growth depends on the threshold used. The RGB value of the seed point is compared with its neighbors, 
         if the difference is smaller then threshold, the image grows.
         . The threshold value is show right side of status bar in QGIS window.
         . Can change the threshold value directly in the value box or by clicking and dragging the mouse.
         Mouse: moving to the right or up, the treshold increases, otherwise it decreases.
         . Using the mouse, clicking and dragging, the image is changed automatically.
         Clicking one time, the image is made with value of threshold.

        - Working with Images of Growth.
         . Show or hide: Use right botton of mouse.
         . Delete the last image: D key.
         . Undo: U Key.
         . Clear: C Key
         . Fill holes: F Key.
         . Poligonize: P Key. *** Create polygon from image ***

        Menu Setup.
        . Select the exists field, text type(will be populate with metadata of tool).
        Metadata: List of visible rasters layers images, user, datetime and scale of map.
        . Virtual area(ha): will be added a expression onto polygon layer for calculate area(ha).

        Menu About.
        . Show information about this plugin.
        . Donation is most welcome!
        </source>
        <translation>
        *** AJUDA - {} ***
        Cria polígono clicando no mapa

        Passos:
        - Criando uma imagem de crescimento.
         . A ferramenta cria uma imagem de crecimento a partir do ponto clicado, ponto de semente, dentro do mapa.
         . O crescimento depende da tolerância usada. Os valores RGB  do ponto semente é comparado com seus vizinhos,
         se a diferença é menor do que a tolerância, a imagem cresce.
         . O valor da tolerância é mostrado no lado direito da barra de status da janela do QGIS.
         . Pode trocar o valor da tolerância diretamente dentro da caixa de valor ou clicando e arrastando o mouse.
         Mouse: movendo para a direita ou acima, a tolerância cresce, caso contrário, diminui.
         . Usando o mouse, clicando e arrastando, a imagem é alterada automaticamente.
         Clicando uma vez, a imagem é feita com o valor da tolerância.

        - Trabalhando com Imagens de crescimento.
         . Mostra e ocultar: Use io botão direito do mouse.
         . Deletar a última imagem: Tecla D.
         . Desfazer: Tecla U.
         . Limpar: Tecla C.
         . Preencher buracos: Tecla F.
         . Poligonalizar: Tecla P. *** Cria o polígono a partir da imagem ***

        Menu Configuração.
        . Seleciona um campo existente, tipo de texto(irá ser populado com os metadado da ferramenta)
        Metadado: Lista de camada de imagens visíveis, usuário, data e horário e escala do mapa.
        . Área(ha) virtual: Irá ser adicionada uma expressão dentro da camada de polígono para o cálculo de área (ha).

        Menu Sobre.
        . Mostra informações sobre esse plugin.
        . Doação é muito bem vinda!
        </translation>
    </message>
</context>
</TS>
