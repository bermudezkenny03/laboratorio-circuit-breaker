-- Tabla mascotas
CREATE TABLE IF NOT EXISTS mascotas (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL,
    tipo       VARCHAR(50)  NOT NULL,
    id_usuario INT          NOT NULL
);

-- Tabla usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id     INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    correo VARCHAR(150) NOT NULL
);

-- Datos de ejemplo
INSERT INTO usuarios (nombre, correo) VALUES
    ('Ana Ramirez',    'ana@petshop.com'),
    ('Diego Herrera',  'diego@petshop.com'),
    ('Sofia Castillo', 'sofia@petshop.com');

INSERT INTO mascotas (nombre, tipo, id_usuario) VALUES
    ('Toby', 'Perro',  1),
    ('Nina', 'Gato',   2),
    ('Kiwi', 'Pajaro', 3),
    ('Max',  'Perro',  1),
    ('Moka', 'Gato',   3);